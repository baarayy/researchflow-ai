"""Builds and holds long-lived dependencies (one per process). No module-level singletons."""

from dataclasses import dataclass

from langchain_core.embeddings import Embeddings
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.graph.nodes import ResearchDeps
from app.ai.graph.workflow import build_workflow
from app.ai.models import ResearchModel, build_research_model
from app.ai.rag.embeddings import build_embeddings
from app.ai.rag.retrieval import DocumentRetriever
from app.ai.tools.web_search import SearchProvider, build_search_provider
from app.core.config import Settings
from app.services.document_service import DocumentIndexer
from app.services.research_service import WorkflowRunner
from app.storage.base import FileStorage
from app.storage.local import LocalFileStorage


@dataclass
class Container:
    settings: Settings
    sessionmaker: async_sessionmaker[AsyncSession]
    storage: FileStorage
    embeddings: Embeddings
    llm: ResearchModel
    search: SearchProvider
    retriever: DocumentRetriever
    graph: CompiledStateGraph
    runner: WorkflowRunner
    indexer: DocumentIndexer
    pool: AsyncConnectionPool | None = None

    async def close(self) -> None:
        await self.runner.shutdown()
        if self.pool is not None:
            await self.pool.close()


async def open_checkpointer(settings: Settings) -> tuple[AsyncPostgresSaver, AsyncConnectionPool]:
    # Settings required by AsyncPostgresSaver: autocommit + dict rows (+ no prepared statements
    # so it also works behind PgBouncer).
    pool = AsyncConnectionPool(
        settings.checkpoint_database_url,
        min_size=1,
        max_size=10,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open()
    saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
    await saver.setup()  # creates/migrates LangGraph's checkpoint tables (idempotent)
    return saver, pool


async def build_container(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    *,
    checkpointer: Checkpointer = None,
    llm: ResearchModel | None = None,
    search: SearchProvider | None = None,
) -> Container:
    pool = None
    if checkpointer is None:
        checkpointer, pool = await open_checkpointer(settings)
    embeddings = build_embeddings(settings)
    storage = LocalFileStorage(settings.upload_dir)
    llm = llm or build_research_model(settings)
    search = search or build_search_provider(settings)
    retriever = DocumentRetriever(
        sessionmaker,
        embeddings,
        top_k=settings.retrieval_top_k,
        min_score=settings.retrieval_min_score,
    )
    graph = build_workflow(ResearchDeps(llm, search, retriever, settings), checkpointer)
    return Container(
        settings=settings,
        sessionmaker=sessionmaker,
        storage=storage,
        embeddings=embeddings,
        llm=llm,
        search=search,
        retriever=retriever,
        graph=graph,
        runner=WorkflowRunner(graph, sessionmaker, settings),
        indexer=DocumentIndexer(sessionmaker, embeddings, storage, settings),
        pool=pool,
    )
