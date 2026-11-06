"""Strict scorecard construction and validation for semantic evaluations."""

from __future__ import annotations

from collections.abc import Mapping

from evaluation.schema import (
    CategoryScore,
    Rubric,
    RunRecord,
    Scorecard,
    validate_run_record,
)


_SCORECARD_KEYS = {
    "schema_version",
    "scenario_id",
    "categories",
    "critical_failures",
}
_CATEGORY_KEYS = {"identifier", "score", "evidence_turns", "rationale"}


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} must contain exactly {sorted(expected)}")


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _array(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def validate_scorecard(scorecard: Scorecard, rubric: Rubric, record: RunRecord) -> None:
    """Validate one complete pedagogy scorecard against its rubric and run."""
    validate_run_record(record, rubric)
    if record.stop_reason == "infrastructure_failure" or record.infrastructure_failure is not None:
        raise ValueError("infrastructure records must not have a scorecard")
    if (
        isinstance(scorecard.schema_version, bool)
        or not isinstance(scorecard.schema_version, int)
        or scorecard.schema_version != rubric.schema_version
    ):
        raise ValueError("scorecard schema version does not match the rubric")
    if not isinstance(scorecard.scenario_id, str) or scorecard.scenario_id != record.scenario_id:
        raise ValueError("scorecard scenario does not match the run record")

    expected = tuple(category.identifier for category in rubric.categories)
    actual = tuple(category.identifier for category in scorecard.categories)
    if len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise ValueError("scorecard must contain every rubric category exactly once")

    valid_turns = {turn.number for turn in record.turns}
    for category in scorecard.categories:
        if (
            isinstance(category.score, bool)
            or not isinstance(category.score, int)
            or category.score not in rubric.allowed_scores
        ):
            raise ValueError(f"category {category.identifier!r} has an invalid score")
        if not category.evidence_turns:
            raise ValueError(f"category {category.identifier!r} requires evidence turns")
        if len(category.evidence_turns) != len(set(category.evidence_turns)):
            raise ValueError(f"category {category.identifier!r} repeats an evidence turn")
        if any(
            isinstance(turn, bool) or not isinstance(turn, int) or turn not in valid_turns
            for turn in category.evidence_turns
        ):
            raise ValueError(f"category {category.identifier!r} references an invalid turn")
        if not isinstance(category.rationale, str) or not category.rationale.strip():
            raise ValueError(f"category {category.identifier!r} requires a rationale")

    if len(scorecard.critical_failures) != len(set(scorecard.critical_failures)):
        raise ValueError("critical failures must not contain duplicates")
    if any(failure not in rubric.critical_failures for failure in scorecard.critical_failures):
        raise ValueError("scorecard contains an unknown critical failure")


def scorecard_from_mapping(
    value: Mapping[str, object],
    rubric: Rubric,
    record: RunRecord,
) -> Scorecard:
    """Parse an exact-key private scorecard document and validate its evidence."""
    document = _object(value, "scorecard")
    _exact_keys(document, _SCORECARD_KEYS, "scorecard")
    schema_version = _integer(document["schema_version"], "scorecard.schema_version")
    scenario_id = _string(document["scenario_id"], "scorecard.scenario_id")

    raw_categories = _array(document["categories"], "scorecard.categories")
    categories: list[CategoryScore] = []
    for index, raw_category in enumerate(raw_categories):
        label = f"scorecard.categories[{index}]"
        category = _object(raw_category, label)
        _exact_keys(category, _CATEGORY_KEYS, label)
        raw_turns = _array(category["evidence_turns"], f"{label}.evidence_turns")
        categories.append(
            CategoryScore(
                identifier=_string(category["identifier"], f"{label}.identifier"),
                score=_integer(category["score"], f"{label}.score"),  # type: ignore[arg-type]
                evidence_turns=tuple(
                    _integer(turn, f"{label}.evidence_turns[{turn_index}]")
                    for turn_index, turn in enumerate(raw_turns)
                ),
                rationale=_string(category["rationale"], f"{label}.rationale"),
            )
        )

    raw_failures = _array(document["critical_failures"], "scorecard.critical_failures")
    scorecard = Scorecard(
        schema_version=schema_version,
        scenario_id=scenario_id,
        categories=tuple(categories),
        critical_failures=tuple(
            _string(failure, f"scorecard.critical_failures[{index}]")
            for index, failure in enumerate(raw_failures)
        ),
    )
    validate_scorecard(scorecard, rubric, record)
    return scorecard


def interactive_score(record: RunRecord, rubric: Rubric) -> Scorecard:
    """Collect one complete scorecard from the implementing evaluator."""
    if record.stop_reason == "infrastructure_failure" or record.infrastructure_failure is not None:
        raise ValueError("infrastructure records must not be scored")

    categories: list[CategoryScore] = []
    for category in rubric.categories:
        score = _integer(
            int(input(f"{category.label} score {rubric.allowed_scores}: ").strip()),
            f"{category.identifier}.score",
        )
        evidence_text = input(f"{category.label} evidence turns (comma-separated): ").strip()
        try:
            evidence_turns = tuple(
                int(item.strip()) for item in evidence_text.split(",") if item.strip()
            )
        except ValueError:
            raise ValueError("evidence turns must be comma-separated integers") from None
        rationale = input(f"{category.label} rationale: ")
        categories.append(
            CategoryScore(
                identifier=category.identifier,
                score=score,  # type: ignore[arg-type]
                evidence_turns=evidence_turns,
                rationale=rationale,
            )
        )

    failures_text = input("Critical failures (comma-separated, blank for none): ").strip()
    scorecard = Scorecard(
        schema_version=rubric.schema_version,
        scenario_id=record.scenario_id,
        categories=tuple(categories),
        critical_failures=tuple(
            item.strip() for item in failures_text.split(",") if item.strip()
        ),
    )
    validate_scorecard(scorecard, rubric, record)
    return scorecard
