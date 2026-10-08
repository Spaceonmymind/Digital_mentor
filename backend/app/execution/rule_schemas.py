from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RuleStatus = Literal["PASS", "PARTIAL", "FAIL", "NOT_APPLICABLE", "NOT_CHECKED"]
VerificationBasis = Literal[
    "DIRECT_EVIDENCE", "DETERMINISTIC_CHECK", "THEMATIC_SEARCH_NOT_FOUND",
    "INSUFFICIENT_CONTEXT", "EXTERNAL_VERIFICATION_REQUIRED",
]


class RuleEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: str | None = None
    page: int | None = None
    section: str | None = None
    block_index: int | None = None


class RuleCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_code: str
    criterion_code: str
    title: str
    status: RuleStatus
    finding: str
    recommendation: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    evidence: list[RuleEvidence] = Field(default_factory=list)
    source_type: str | None = None
    source_document: str | None = None
    source_section: str | None = None
    source_pages: list[int] = Field(default_factory=list)
    methodology_owner: str | None = None
    methodology_version: str | None = None
    is_official: bool | None = None
    authority: str | None = None
    verification_basis: VerificationBasis | None = None
    searched_context: list[str] = Field(default_factory=list)
    capability: str
    normative_strength: Literal["REQUIRED", "CONDITIONAL", "RECOMMENDED", "OPTIONAL"]
    score_weight: float = Field(default=1.0, ge=0)


class CandidateAgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_code: str
    summary: str
    rule_results: list[RuleCheckResult]
    strengths: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class CompactRuleCheck(BaseModel):
    """Provider-facing rule result; methodology metadata is restored server-side."""

    model_config = ConfigDict(extra="forbid")

    rule_code: str
    status: RuleStatus
    finding: str
    recommendation: str | None = None
    evidence: list[RuleEvidence] = Field(default_factory=list)
    verification_basis: VerificationBasis | None = None
    searched_context: list[str] = Field(default_factory=list)


class CompactAcademicAgentOutput(BaseModel):
    """Small structured response used by thematic academic agents."""

    model_config = ConfigDict(extra="forbid")

    criterion_code: str
    summary: str
    rule_results: list[CompactRuleCheck]


class CandidateFinalOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    strengths: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    represented_result: str | None = None


# Neutral aliases used by new rule-based methodologies. The original names stay
# available so CANDIDATE_DISSERTATION keeps its existing JSON schema contract.
RuleBasedAgentOutput = CandidateAgentOutput
RuleBasedFinalOutput = CandidateFinalOutput
