"""Offline search provider for demo mode and tests.

The corpus is a handful of clearly labelled demo fixtures on the reserved `.invalid` domain, so
nobody can mistake them for real sources. Matching is plain keyword overlap: queries that share
no meaningful words with the corpus return no results, which exercises the empty-result paths.
"""

from app.ai.rag.embeddings import tokenize
from app.ai.tools.web_search import WebResult

DEMO_CORPUS: list[dict[str, str]] = [
    {
        "title": "[Demo fixture] Open-weight model licensing overview",
        "url": "https://demo.researchflow.invalid/licensing-overview",
        "published_date": "2026-03-02",
        "content": (
            "Open-weight language models are distributed under different licenses. Permissive "
            "licenses such as Apache 2.0 and MIT allow commercial use, modification and "
            "redistribution. Some model licenses add acceptable-use policies or user-count "
            "thresholds, so production teams should review license terms before deployment."
        ),
    },
    {
        "title": "[Demo fixture] Estimating GPU memory for LLM inference",
        "url": "https://demo.researchflow.invalid/gpu-memory",
        "published_date": "2025-11-18",
        "content": (
            "Hardware requirements for LLM inference are dominated by GPU memory for the model "
            "weights. At 16-bit precision each parameter needs "
            "two bytes, so a 70 billion parameter model needs roughly 140 GB for weights alone. "
            "4-bit quantization reduces weight memory by about four times, with some loss of "
            "accuracy. The KV cache adds memory that grows with context length and batch size."
        ),
    },
    {
        "title": "[Demo fixture] Evaluating reasoning in language model agents",
        "url": "https://demo.researchflow.invalid/agent-reasoning-evals",
        "published_date": "2026-05-20",
        "content": (
            "Agent benchmarks measure multi-step reasoning, tool calling accuracy and recovery "
            "from errors. Static benchmark scores can be inflated by training data "
            "contamination, so teams increasingly evaluate open models on their own tasks. "
            "Reliable tool calling and structured output matter more for agents than raw "
            "benchmark rank."
        ),
    },
    {
        "title": "[Demo fixture] Production readiness checklist for self-hosted LLMs",
        "url": "https://demo.researchflow.invalid/production-checklist",
        "published_date": "2026-01-09",
        "content": (
            "Production use of self-hosted models requires monitoring latency, throughput and "
            "error rates. Serving engines with continuous batching improve throughput. Teams "
            "should plan for model updates, security patching, prompt injection defences and "
            "evaluation pipelines before production launch. Known risks and limitations of agents "
            "include hallucinated tool arguments, cost overruns from long loops and unclear "
            "accountability for automated actions."
        ),
    },
    {
        "title": "[Demo fixture] Retrieval-augmented generation basics",
        "url": "https://demo.researchflow.invalid/rag-basics",
        "published_date": "2024-02-14",
        "content": (
            "Retrieval-augmented generation retrieves relevant document chunks with vector "
            "search and passes them to the model as context. Chunk size, overlap and the "
            "number of retrieved passages affect answer quality. Grounded answers should cite "
            "the passages they use and admit when the documents lack the answer."
        ),
    },
    {
        "title": "[Demo fixture] Agent frameworks and workflow orchestration",
        "url": "https://demo.researchflow.invalid/agent-orchestration",
        "published_date": "2026-06-30",
        "content": (
            "Explicit workflow graphs make agent behaviour easier to test than a single "
            "free-running agent loop. State machines with checkpoints allow long-running "
            "workflows to pause for human approval and resume later. Iteration limits prevent "
            "runaway loops and control cost."
        ),
    },
]


def _score(query_tokens: set[str], doc: dict[str, str]) -> int:
    return len(query_tokens & set(tokenize(doc["title"] + " " + doc["content"])))


class MockSearchProvider:
    name = "mock"

    def __init__(self, corpus: list[dict[str, str]] | None = None, min_overlap: int = 2):
        self.corpus = DEMO_CORPUS if corpus is None else corpus
        self.min_overlap = min_overlap

    async def search(self, query: str, max_results: int) -> list[WebResult]:
        tokens = set(tokenize(query))
        scored = sorted(
            ((s, d) for d in self.corpus if (s := _score(tokens, d)) >= self.min_overlap),
            key=lambda pair: pair[0],
            reverse=True,
        )
        return [
            WebResult(
                title=d["title"],
                url=d["url"],
                content=d["content"],
                content_kind="snippet",
                published_date=d.get("published_date"),
                score=float(s),
            )
            for s, d in scored[:max_results]
        ]
