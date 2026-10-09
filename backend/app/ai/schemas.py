"""Pydantic schemas for LLM structured output.

These are the contracts between graph nodes and the model. LangChain's
`with_structured_output(Schema)` asks the model to fill them, and Pydantic validates the
result, so malformed output becomes an exception instead of a silently bad state.
Field descriptions are sent to the model, so they double as instructions.
"""

from typing import Literal

from pydantic import BaseModel, Field

SourcePreference = Literal["web", "documents"]


class PlannedTask(BaseModel):
    question: str = Field(description="A focused, independently researchable subquestion.")
    rationale: str = Field(description="Why answering it matters for the main question.")
    evidence_type: str = Field(
        description="Kind of evidence needed, e.g. 'benchmark data', 'license terms', "
        "'expert analysis', 'definitions'."
    )
    preferred_sources: list[SourcePreference] = Field(
        description="Where this evidence is most likely found."
    )


class ResearchPlan(BaseModel):
    objective: str = Field(description="One-sentence restatement of what the research must answer.")
    tasks: list[PlannedTask] = Field(min_length=1, max_length=8)


class ExtractedClaim(BaseModel):
    source_id: str = Field(description="The id attribute of the <source> the claim comes from.")
    task_id: str = Field(description="The research task this claim helps answer.")
    claim: str = Field(description="A factual statement made by the source, in your own words.")
    quote: str | None = Field(
        default=None, description="A short verbatim excerpt from the source supporting the claim."
    )
    confidence: float = Field(ge=0, le=1, description="How directly the source supports the claim.")


class Contradiction(BaseModel):
    description: str
    source_ids: list[str]


class EvidenceAnalysis(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    unsupported_or_weak: list[str] = Field(
        default_factory=list, description="Claims in the sources that lack support or are vague."
    )
    gaps: list[str] = Field(default_factory=list, description="Information still missing.")
    outdated_source_ids: list[str] = Field(default_factory=list)
    summary: str = Field(default="", description="Two or three sentences on what was learned.")


class TaskCoverage(BaseModel):
    task_id: str
    covered: bool
    note: str = ""


class GapQuery(BaseModel):
    question: str = Field(description="A new, specific subquestion that would close a gap.")
    rationale: str


class CriticAssessment(BaseModel):
    task_coverage: list[TaskCoverage]
    evidence_quality: Literal["low", "medium", "high"]
    citation_completeness: float = Field(
        ge=0, le=1, description="Share of key points that are backed by a cited source."
    )
    remaining_gaps: list[GapQuery] = Field(default_factory=list, max_length=4)
    needs_more_research: bool
    summary: str


class ReportFinding(BaseModel):
    heading: str
    statement: str
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="Ids (E-...) of evidence items that support the statement.",
    )
    kind: Literal["fact", "inference"] = Field(
        description="'fact' if directly supported by cited evidence; 'inference' if it is your "
        "own conclusion drawn from the evidence."
    )


class ComparisonTable(BaseModel):
    title: str
    columns: list[str] = Field(min_length=2)
    rows: list[list[str]]


class ReportDraft(BaseModel):
    executive_summary: str
    methodology: str
    findings: list[ReportFinding]
    comparison_table: ComparisonTable | None = None
    contradictions_and_uncertainties: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    conclusions: str


class GroundedAnswer(BaseModel):
    answer: str
    cited_passage_ids: list[str] = Field(default_factory=list)
    sufficient_evidence: bool = Field(
        description="False if the passages do not contain enough information to answer."
    )
