"""Basic RAG: retrieve passages, answer only from them, validate the cited passage ids.

This is the simplest grounded-answer pipeline in the project (learning guide, stage 6). The
research graph uses the same retriever, but adds planning, iteration and critique around it.
"""

from dataclasses import dataclass

from app.ai.models import ResearchModel
from app.ai.prompts import GROUNDED_ANSWER, fence
from app.ai.rag.retrieval import DocumentRetriever, RetrievalFilters, RetrievedPassage
from app.ai.schemas import GroundedAnswer

NOT_FOUND = "The documents do not contain enough information to answer this question."


@dataclass
class AnswerResult:
    answer: str
    sufficient_evidence: bool
    cited: list[tuple[str, RetrievedPassage]]


async def answer_from_documents(
    llm: ResearchModel,
    retriever: DocumentRetriever,
    question: str,
    filters: RetrievalFilters,
    top_k: int | None = None,
) -> AnswerResult:
    passages = await retriever.retrieve(question, filters, top_k=top_k)
    if not passages:  # nothing retrieved: don't even ask the model
        return AnswerResult(NOT_FOUND, False, [])
    labelled = {f"P{i}": p for i, p in enumerate(passages, start=1)}
    rendered = "\n\n".join(
        fence(pid, p.text, file=p.filename, page=p.page_number) for pid, p in labelled.items()
    )
    result = await llm.structured(
        GroundedAnswer,
        GROUNDED_ANSWER,
        {"question": question, "passages": rendered},
        context={
            "question": question,
            "passages": [{"id": k, "text": p.text} for k, p in labelled.items()],
        },
    )
    cited = [
        (pid, labelled[pid]) for pid in dict.fromkeys(result.cited_passage_ids) if pid in labelled
    ]
    sufficient = result.sufficient_evidence and bool(cited)  # an uncited answer is not grounded
    return AnswerResult(result.answer if sufficient else NOT_FOUND, sufficient, cited)
