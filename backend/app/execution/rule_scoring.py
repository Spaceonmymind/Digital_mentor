from dataclasses import dataclass

from app.execution.rule_schemas import RuleCheckResult


SCORE_VALUE = {"PASS": 1.0, "PARTIAL": 0.5, "FAIL": 0.0}


@dataclass(frozen=True)
class CriterionScore:
    score: int | None
    max_score: int | None
    status: str
    checked_weight: float
    applicable_weight: float


def rule_is_scored(rule: RuleCheckResult) -> bool:
    if rule.status not in SCORE_VALUE:
        return False
    return rule.normative_strength in {"REQUIRED", "CONDITIONAL"}


def score_criterion(rules: list[RuleCheckResult], max_score: int = 10) -> CriterionScore:
    applicable = [
        rule
        for rule in rules
        if rule.normative_strength in {"REQUIRED", "CONDITIONAL"}
        and rule.status != "NOT_APPLICABLE"
    ]
    scored = [rule for rule in applicable if rule_is_scored(rule)]
    denominator = sum(rule.score_weight for rule in scored)
    applicable_weight = sum(rule.score_weight for rule in applicable)
    if denominator <= 0:
        return CriterionScore(None, None, "NOT_CHECKED", 0.0, applicable_weight)
    numerator = sum(rule.score_weight * SCORE_VALUE[rule.status] for rule in scored)
    score = int(round(max_score * numerator / denominator))
    status = "PASS" if score >= 8 else "PARTIAL" if score >= 4 else "FAIL"
    return CriterionScore(score, max_score, status, denominator, applicable_weight)


def score_methodology(criteria: dict[str, list[RuleCheckResult]], criterion_max_score: int = 10) -> dict:
    criterion_scores = {code: score_criterion(rules, criterion_max_score) for code, rules in criteria.items()}
    evaluated = [item for item in criterion_scores.values() if item.score is not None]
    checked_weight = sum(item.checked_weight for item in criterion_scores.values())
    applicable_weight = sum(item.applicable_weight for item in criterion_scores.values())
    return {
        "criteria": criterion_scores,
        "overall_score": sum(item.score or 0 for item in evaluated),
        "evaluated_max_score": sum(item.max_score or 0 for item in evaluated),
        "nominal_max_score": len(criteria) * criterion_max_score,
        "coverage": round(checked_weight / applicable_weight, 4) if applicable_weight else 0.0,
    }
