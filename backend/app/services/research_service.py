"""Research sessions: create, run the LangGraph workflow in the background, approve/resume.

How a run is observed: the runner consumes `graph.astream(..., stream_mode="updates")`. After
each node it (1) appends a `workflow_events` row and (2) projects the checkpointed state into
the tasks/sources/evidence tables. The SSE endpoint streams those rows, so the UI only ever shows
real, persisted progress.

Durability: LangGraph checkpoints every step to Postgres under thread_id = session id. A run that
was interrupted for approval can be resumed by any process, including after a restart, and runs
that were mid-flight when the server stopped are resumed from their last checkpoint on startup.
"""

import asyncio
import logging
import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.graph.state import ResearchState
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailed
from app.core.logging import session_id_var
from app.models import ResearchSession
from app.repositories import documents as doc_repo
from app.repositories import research as repo
from app.schemas.research import ApprovalDecision, CreateResearchRequest

logger = logging.getLogger(__name__)

REPORT_TO_SESSION_STATUS = {
    "complete": "completed",
    "partial": "partial",
    "insufficient_evidence": "partial",
}


def _summarize(node: str, delta: dict[str, Any] | None) -> dict[str, Any]:
    """Small, UI-friendly payload for a node event (never the whole state)."""
    d = delta or {}
    match node:
        case "planner":
            return {
                "task_count": len([t for t in d.get("tasks", []) if t["status"] != "dropped"]),
                "failed": d.get("status") == "failed",
            }
        case "plan_review":
            return {"approved": d.get("plan_approved", False)}
        case "dispatcher":
            return {"iteration": d.get("iteration"), "tool_calls": d.get("planned_calls", [])}
        case "web_researcher" | "document_researcher":
            log = (d.get("search_log") or [{}])[0]
            return {
                "query": log.get("query"),
                "task_id": log.get("task_id"),
                "status": log.get("status"),
                "result_count": log.get("result_count", 0),
            }
        case "evidence_analyzer":
            return {"new_evidence": len(d.get("evidence", []))}
        case "critic":
            c = d.get("critic") or {}
            return {
                k: c.get(k) for k in ("coverage", "evidence_quality", "sufficient", "summary")
            } | {"new_tasks": len([t for t in d.get("tasks", []) if t["status"] == "pending"])}
        case "report_review":
            return {"approved": d.get("report_approved", False)}
        case "report_generator":
            return {"status": (d.get("final_report") or {}).get("status")}
    return {}


class WorkflowRunner:
    def __init__(
        self,
        graph: CompiledStateGraph,
        sessionmaker: async_sessionmaker[AsyncSession],
        settings: Settings,
    ):
        self.graph = graph
        self.sessionmaker = sessionmaker
        self.settings = settings
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}

    @staticmethod
    def config(session_id: uuid.UUID) -> RunnableConfig:
        return {"configurable": {"thread_id": str(session_id)}, "recursion_limit": 200}

    def is_running(self, session_id: uuid.UUID) -> bool:
        task = self._tasks.get(session_id)
        return task is not None and not task.done()

    def start(self, session_id: uuid.UUID, command: Command | None = None) -> bool:
        """Schedule a run (or resume). Returns False if one is already active in this process."""
        if self.is_running(session_id):
            return False
        task = asyncio.create_task(self._run(session_id, command), name=f"research-{session_id}")
        self._tasks[session_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(session_id, None))
        return True

    async def wait(self, session_id: uuid.UUID) -> None:
        if task := self._tasks.get(session_id):
            await asyncio.shield(task)

    async def shutdown(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)

    def initial_state(self, s: ResearchSession) -> ResearchState:
        return {
            "session_id": str(s.id),
            "owner_id": s.owner_id,
            "question": s.question,
            "options": s.options,  # type: ignore[typeddict-item]
            "limits": {
                "max_iterations": s.max_iterations,
                "max_tool_calls": self.settings.max_tool_calls_per_session,
                "max_tasks": self.settings.max_tasks_per_session,
                "coverage_threshold": self.settings.coverage_threshold,
            },
            "iteration": 0,
            "tool_calls_used": 0,
        }

    async def _graph_input(self, session_id: uuid.UUID, command: Command | None) -> Any:
        if command is not None:
            return command
        snapshot = await self.graph.aget_state(self.config(session_id))
        if snapshot.values:
            return None  # resume from the last checkpoint
        async with self.sessionmaker() as db:
            session = await repo.get_session(db, session_id)
            if session is None:
                raise NotFoundError("Research session not found")
            return self.initial_state(session)

    async def _run(self, session_id: uuid.UUID, command: Command | None) -> None:
        session_id_var.set(str(session_id))
        config = self.config(session_id)
        try:
            graph_input = await self._graph_input(session_id, command)
            async with self.sessionmaker() as db:
                await repo.update_session(db, session_id, status="running", error=None)
                await repo.add_event(
                    db,
                    session_id,
                    "status",
                    None,
                    {"status": "running", "resumed": command is not None},
                )
                await db.commit()

            async for update in self.graph.astream(graph_input, config, stream_mode="updates"):
                await self._record_update(session_id, update)

            await self._finalize(session_id)
        except asyncio.CancelledError:
            logger.info("Run cancelled (shutdown); it will resume from its checkpoint on restart")
            raise
        except Exception as exc:
            logger.exception("Workflow failed")
            async with self.sessionmaker() as db:
                await repo.update_session(
                    db, session_id, status="failed", error=f"Workflow error ({type(exc).__name__})."
                )
                await repo.add_event(
                    db,
                    session_id,
                    "error",
                    None,
                    {"message": "The research workflow failed unexpectedly."},
                )
                await db.commit()

    async def _record_update(self, session_id: uuid.UUID, update: dict[str, Any]) -> None:
        snapshot = await self.graph.aget_state(self.config(session_id))
        values: dict[str, Any] = snapshot.values or {}
        async with self.sessionmaker() as db:
            for node, delta in update.items():
                if node == "__interrupt__":
                    payload = delta[0].value
                    await repo.update_session(
                        db,
                        session_id,
                        status="awaiting_approval",
                        stage=payload["kind"],
                        pending_approval=payload,
                    )
                    await repo.add_event(
                        db, session_id, "interrupt", payload["kind"], {"kind": payload["kind"]}
                    )
                else:
                    await repo.add_event(db, session_id, "node", node, _summarize(node, delta))
                    await repo.update_session(db, session_id, stage=node)
            # Projection of the checkpointed state (idempotent upserts).
            await repo.upsert_tasks(db, session_id, values.get("tasks", []))
            await repo.upsert_sources(db, session_id, list(values.get("sources", {}).values()))
            await repo.insert_evidence(db, session_id, values.get("evidence", []))
            await repo.update_session(
                db,
                session_id,
                iteration=values.get("iteration", 0),
                critic_feedback=values.get("critic"),
            )
            await db.commit()

    async def _finalize(self, session_id: uuid.UUID) -> None:
        snapshot = await self.graph.aget_state(self.config(session_id))
        if snapshot.next:  # paused at an interrupt; status was set when it was recorded
            return
        values = snapshot.values or {}
        async with self.sessionmaker() as db:
            if values.get("status") == "failed" or not values.get("final_report"):
                message = next(
                    (e["message"] for e in values.get("errors", []) if not e["recoverable"]),
                    "The workflow ended without a report.",
                )
                await repo.update_session(
                    db, session_id, status="failed", error=message, stage="failed"
                )
                await repo.add_event(db, session_id, "error", None, {"message": message})
            else:
                report = values["final_report"]
                status = REPORT_TO_SESSION_STATUS[report["status"]]
                await repo.save_report(db, session_id, report)
                await repo.update_session(
                    db, session_id, status=status, stage="done", pending_approval=None
                )
                await repo.add_event(
                    db,
                    session_id,
                    "status",
                    None,
                    {"status": status, "report_status": report["status"]},
                )
            await db.commit()

    async def recover(self) -> int:
        """On startup: resume runs that were in flight when the process stopped."""
        async with self.sessionmaker() as db:
            stale = await repo.sessions_with_status(db, ("queued", "running"))
        for s in stale:
            logger.info("Recovering research session %s from checkpoint", s.id)
            self.start(s.id)
        return len(stale)


class ResearchService:
    def __init__(self, db: AsyncSession, runner: WorkflowRunner, settings: Settings):
        self.db = db
        self.runner = runner
        self.settings = settings

    async def create(
        self, owner_id: str, req: CreateResearchRequest, idempotency_key: str | None
    ) -> tuple[ResearchSession, bool]:
        """Returns (session, created). A repeated Idempotency-Key returns the original session."""
        if idempotency_key and (
            existing := await repo.get_by_idempotency_key(self.db, owner_id, idempotency_key)
        ):
            return existing, False
        wanted = set(req.document_ids or [])
        if wanted and await doc_repo.count_owned(self.db, owner_id, list(wanted)) != len(wanted):
            raise ValidationFailed("One or more document_ids do not exist")
        session = ResearchSession(
            owner_id=owner_id,
            question=req.question.strip(),
            status="queued",
            max_iterations=min(
                req.max_iterations or self.settings.max_research_iterations,
                self.settings.max_research_iterations,
            ),
            options={
                "use_web": req.use_web,
                "use_documents": req.use_documents,
                "document_ids": [str(d) for d in req.document_ids]
                if req.document_ids is not None
                else None,
                "require_plan_approval": req.require_plan_approval,
                "require_report_approval": req.require_report_approval,
            },
            idempotency_key=idempotency_key,
        )
        self.db.add(session)
        try:
            await self.db.commit()
        except IntegrityError:  # concurrent request with the same key won the race
            await self.db.rollback()
            existing = await repo.get_by_idempotency_key(self.db, owner_id, idempotency_key or "")
            if existing is None:
                raise
            return existing, False
        self.runner.start(session.id)
        return session, True

    async def get(self, owner_id: str, session_id: uuid.UUID) -> ResearchSession:
        session = await repo.get_session(self.db, session_id, owner_id)
        if session is None:
            raise NotFoundError("Research session not found")
        return session

    async def resume(
        self, owner_id: str, session_id: uuid.UUID, decision: ApprovalDecision
    ) -> ResearchSession:
        session = await self.get(owner_id, session_id)
        if session.status != "awaiting_approval":
            raise ConflictError(f"Session is not awaiting approval (status: {session.status})")
        # Atomic claim: a double-clicked approve or retried request resumes the graph only once.
        if not await repo.claim_for_resume(self.db, session_id, owner_id):
            raise ConflictError("This approval was already submitted")
        await repo.add_event(self.db, session_id, "approval", None, decision.model_dump())
        await self.db.commit()
        self.runner.start(session_id, Command(resume=decision.model_dump()))
        await self.db.refresh(session)
        return session
