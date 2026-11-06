"""Deterministic, sanitized rendering for semantic baseline evidence."""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from evaluation.isolation import (
    RULE_MARKERS,
    USER_HOME_RULE_PATHS,
    RuleDisclosure,
)
from evaluation.sanitize import RedactionRule, assert_tracked_safe, sanitize_text
from evaluation.schema import (
    Finding,
    RunRecord,
    Scorecard,
    TurnRecord,
    validate_run_record,
)


TITLE = "# Antigravity Semantic Baseline — 2026-11-06"
PRIVACY_STATEMENT = (
    "Raw Antigravity streams, runtime logs, provider metadata, and evaluator notes "
    "remain only under ignored .semantic-runs/. Temporary learner homes and working "
    "directories were created outside the repository and deleted after private run "
    "records were saved. This tracked report contains fictitious scenario data and "
    "the minimum sanitized excerpts needed to justify its scores."
)
LIMITATIONS_STATEMENT = (
    "User-level and above-home runtime rules were inherited with authentication; "
    "only their names were recorded, never their contents."
)
HEADINGS = (
    "## Evaluation identity",
    "## Scenario results",
    "## General findings",
    "## Scenario-specific findings",
    "## Infrastructure results",
    "## Privacy statement",
    "## Baseline limitations",
)
_FINDING_CLASSES = {
    "pedagogy",
    "launcher_ux",
    "documentation",
    "runtime",
    "infrastructure",
}
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_EVIDENCE_REFERENCE = re.compile(r"^([a-z][a-z0-9]*(?:-[a-z0-9]+)*):([1-9][0-9]*)$")
_TOTAL_LINE = re.compile(r"^- Total: ([0-9]+)/([1-9][0-9]*)$")
_CATEGORY_LINE = re.compile(
    r"^  - ([a-z][a-z0-9]*(?:-[a-z0-9]+)*): ([0-2])/2$"
)
_TURN_LIST = re.compile(r"^[1-9][0-9]*(?:, [1-9][0-9]*)*$")
_EVIDENCE_HEADING = re.compile(r"^### Evidence turn ([1-9][0-9]*)$")
_LIMITATION_LINE = re.compile(
    r"^- ([a-z][a-z0-9]*(?:-[a-z0-9]+)*): user-home rule paths: (.+); "
    r"above-home markers: (.+)$"
)
_ABOVE_HOME_MARKER = re.compile(
    r"^([^,]+) \(([1-9][0-9]*) (level|levels) above home\)$"
)
_APPROVED_RESEARCH_PATHS = {
    "/papers/details/0adf25e68b4d552aa18c5d2ea631170e/",
    "/papers/details/779761ae76575793a1f13ff9502ee816/",
    "/papers/details/a51cac61d84156638d67764eeadcc18b/",
    "/papers/details/af8af3ac1bde5b5792569dcb8341ff99/",
    "/papers/details/0cb2208439095e43acfd7e71c4619110/",
    "/papers/details/892841916b2f5030b1f42ccda3ff0adc/",
}
_BASELINE_SCENARIO_IDS = frozenset(
    {
        "conceptual-physics",
        "practical-programming",
        "communication-writing",
    }
)


@dataclass(frozen=True)
class ScenarioRuntimeDisclosure:
    scenario_id: str
    local_rule_check_passed: bool
    rule_disclosure: RuleDisclosure


def _inline(text: str) -> str:
    return " ".join(text.split())


def _approved_research_link(link: str) -> bool:
    if not isinstance(link, str):
        return False
    parsed = urlsplit(link)
    return (
        parsed.scheme == "https"
        and parsed.netloc == "consensus.app"
        and parsed.path in _APPROVED_RESEARCH_PATHS
        and not parsed.fragment
        and parsed.query in ("", "utm_source=cursor")
    )


def validate_finding(
    finding: Finding,
    records: Mapping[str, RunRecord],
) -> None:
    if not isinstance(finding.identifier, str) or _IDENTIFIER.fullmatch(finding.identifier) is None:
        raise ValueError("finding identifier must be lowercase and hyphenated")
    if finding.classification not in _FINDING_CLASSES:
        raise ValueError("finding classification is invalid")
    if finding.scope not in ("general", "scenario-specific"):
        raise ValueError("finding scope is invalid")
    if not finding.scenario_ids or len(finding.scenario_ids) != len(set(finding.scenario_ids)):
        raise ValueError("finding scenario IDs must be non-empty and unique")
    if any(scenario_id not in records for scenario_id in finding.scenario_ids):
        raise ValueError("finding references an unknown scenario")
    if finding.classification == "pedagogy" and not finding.evidence_turns:
        raise ValueError("finding requires transcript evidence")
    if len(finding.evidence_turns) != len(set(finding.evidence_turns)):
        raise ValueError("finding evidence turns must not contain duplicates")
    for reference in finding.evidence_turns:
        match = _EVIDENCE_REFERENCE.fullmatch(reference)
        if match is None or match.group(1) not in finding.scenario_ids:
            raise ValueError("finding contains an invalid evidence reference")
        record = records[match.group(1)]
        if int(match.group(2)) not in {turn.number for turn in record.turns}:
            raise ValueError("finding references an unavailable evidence turn")
    if not isinstance(finding.summary, str) or not finding.summary.strip():
        raise ValueError("finding summary must be non-empty")
    if finding.classification == "pedagogy":
        if not finding.research_links or not all(
            _approved_research_link(link) for link in finding.research_links
        ):
            raise ValueError("pedagogy findings require approved research links")
    elif any(not isinstance(link, str) or not link.strip() for link in finding.research_links):
        raise ValueError("finding research links must be non-empty strings")


def finding_from_mapping(
    value: Mapping[str, object],
    records: Mapping[str, RunRecord],
) -> Finding:
    """Parse and validate one exact-key private finding document."""
    expected = {
        "identifier",
        "classification",
        "scope",
        "scenario_ids",
        "evidence_turns",
        "summary",
        "research_links",
    }
    if set(value) != expected:
        raise ValueError("finding has an invalid shape")

    def strings(field: str, *, non_empty: bool) -> tuple[str, ...]:
        raw = value[field]
        if not isinstance(raw, list) or any(
            not isinstance(item, str) or not item.strip() for item in raw
        ):
            raise ValueError(f"finding {field} must be a list of non-empty strings")
        if non_empty and not raw:
            raise ValueError(f"finding {field} must not be empty")
        return tuple(raw)

    identifier = value["identifier"]
    classification = value["classification"]
    scope = value["scope"]
    summary = value["summary"]
    if not all(
        isinstance(item, str)
        for item in (identifier, classification, scope, summary)
    ):
        raise ValueError("finding scalar fields must be strings")
    finding = Finding(
        identifier=identifier,
        classification=classification,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        scenario_ids=strings("scenario_ids", non_empty=True),
        evidence_turns=strings("evidence_turns", non_empty=False),
        summary=summary,
        research_links=strings("research_links", non_empty=False),
    )
    validate_finding(finding, records)
    return finding


def _validated_disclosure(
    scenario_id: str,
    runtime_disclosures: Mapping[str, ScenarioRuntimeDisclosure],
) -> RuleDisclosure:
    disclosure = runtime_disclosures.get(scenario_id)
    if disclosure is None or disclosure.scenario_id != scenario_id:
        raise ValueError("run record is missing its runtime disclosure")
    if disclosure.local_rule_check_passed is not True:
        raise ValueError("runtime disclosure does not confirm the local rule check")
    rules = disclosure.rule_disclosure
    if rules.boundary not in ("user_home", "filesystem_root"):
        raise ValueError("runtime disclosure has an invalid rule boundary")
    if any(path not in USER_HOME_RULE_PATHS for path in rules.user_home_rule_paths):
        raise ValueError("runtime disclosure contains an unknown user-home rule path")
    if len(rules.user_home_rule_paths) != len(set(rules.user_home_rule_paths)):
        raise ValueError("runtime disclosure repeats a user-home rule path")
    for marker in rules.above_home_markers:
        if (
            isinstance(marker.levels_above_home, bool)
            or not isinstance(marker.levels_above_home, int)
            or marker.levels_above_home < 1
            or marker.marker not in RULE_MARKERS
        ):
            raise ValueError("runtime disclosure contains an invalid above-home marker")
    marker_keys = tuple(
        (marker.levels_above_home, marker.marker)
        for marker in rules.above_home_markers
    )
    if len(marker_keys) != len(set(marker_keys)):
        raise ValueError("runtime disclosure repeats an above-home marker")
    return rules


def _quote(turn: TurnRecord) -> list[str]:
    if len(turn.learner) > 600 or len(turn.tutor) > 600:
        raise ValueError("report quotations must not exceed 600 characters per turn")
    return [
        f"### Evidence turn {turn.number}",
        f"> Learner: {_inline(turn.learner)}",
        f"> Tutor: {_inline(turn.tutor)}",
        "",
    ]


def _finding_lines(findings: Sequence[Finding]) -> list[str]:
    if not findings:
        return ["- None.", ""]
    lines: list[str] = []
    for finding in findings:
        lines.extend(
            [
                f"### {finding.identifier}",
                f"- Classification: {finding.classification}",
                f"- Scenarios: {', '.join(finding.scenario_ids)}",
                f"- Evidence: {', '.join(finding.evidence_turns)}",
                f"- Summary: {_inline(finding.summary)}",
                (
                    f"- Research: {', '.join(finding.research_links)}"
                    if finding.research_links
                    else "- Research: none"
                ),
                "",
            ]
        )
    return lines


def render_baseline_report(
    records: Sequence[RunRecord],
    scorecards: Sequence[Scorecard],
    findings: Sequence[Finding],
    *,
    runtime_disclosures: Mapping[str, ScenarioRuntimeDisclosure],
    rules: Sequence[RedactionRule],
) -> str:
    """Render a deterministic tracked report containing only minimum evidence."""
    scenario_ids = [record.scenario_id for record in records]
    if (
        len(scenario_ids) != len(_BASELINE_SCENARIO_IDS)
        or set(scenario_ids) != _BASELINE_SCENARIO_IDS
    ):
        raise ValueError("run records must contain the exact baseline scenario triplet")
    identity_fields = (
        "suite_id",
        "repository_commit",
        "protocol_version",
        "protocol_sha256",
        "runtime",
        "runtime_version",
        "model_identifier",
    )
    for field in identity_fields:
        if len({getattr(record, field) for record in records}) != 1:
            raise ValueError(f"run records must share {field}")

    record_by_scenario: dict[str, RunRecord] = {}
    for record in records:
        validate_run_record(record)
        if record.scenario_id in record_by_scenario:
            raise ValueError("run records must have unique scenario IDs")
        record_by_scenario[record.scenario_id] = record
        _validated_disclosure(record.scenario_id, runtime_disclosures)
    scorecard_by_scenario: dict[str, Scorecard] = {}
    for scorecard in scorecards:
        if scorecard.scenario_id in scorecard_by_scenario:
            raise ValueError("scorecards must have unique scenario IDs")
        record = record_by_scenario.get(scorecard.scenario_id)
        if record is None:
            raise ValueError("scorecard references an unknown scenario")
        if record.stop_reason == "infrastructure_failure" or record.infrastructure_failure is not None:
            raise ValueError("infrastructure records must not have a scorecard")
        scorecard_by_scenario[scorecard.scenario_id] = scorecard
    for record in records:
        is_infrastructure = (
            record.stop_reason == "infrastructure_failure"
            or record.infrastructure_failure is not None
        )
        if not is_infrastructure and record.scenario_id not in scorecard_by_scenario:
            raise ValueError("successful run record is missing a scorecard")

    finding_identifiers: set[str] = set()
    for finding in findings:
        if finding.identifier in finding_identifiers:
            raise ValueError("finding identifiers must be unique")
        finding_identifiers.add(finding.identifier)
        validate_finding(finding, record_by_scenario)

    lines = [TITLE, "", HEADINGS[0]]
    if records:
        first = records[0]
        lines.extend(
            [
                f"- Suite ID: {first.suite_id}",
                f"- Repository commit: {first.repository_commit}",
                f"- Protocol version: {first.protocol_version}",
                f"- Protocol SHA-256: {first.protocol_sha256}",
                f"- Runtime: {first.runtime}",
                f"- Runtime version: {first.runtime_version}",
                f"- Model: {first.model_identifier}",
            ]
        )
    else:
        lines.append("- No run records.")
    lines.extend(["", HEADINGS[1]])

    for record in records:
        lines.extend(
            [
                f"### {record.scenario_id}",
                f"- Run ID: {record.run_id}",
                f"- Stop reason: {record.stop_reason}",
            ]
        )
        scorecard = scorecard_by_scenario.get(record.scenario_id)
        if scorecard is None:
            lines.extend(
                [
                    f"- Infrastructure failure: {record.infrastructure_failure or 'unspecified'}",
                    "- Score: not assigned",
                    "",
                ]
            )
            continue

        maximum = len(scorecard.categories) * 2
        lines.extend([f"- Total: {scorecard.total}/{maximum}", "- Category scores:"])
        referenced_turns: set[int] = set()
        available_turns = {turn.number for turn in record.turns}
        for category in scorecard.categories:
            if not category.evidence_turns or any(
                turn not in available_turns for turn in category.evidence_turns
            ):
                raise ValueError("scorecard references an invalid evidence turn")
            if not category.rationale.strip():
                raise ValueError("scorecard category rationale must be non-empty")
            referenced_turns.update(category.evidence_turns)
            lines.extend(
                [
                    f"  - {category.identifier}: {category.score}/2",
                    f"    - Rationale: {_inline(category.rationale)}",
                    "    - Evidence turns: "
                    + ", ".join(str(turn) for turn in category.evidence_turns),
                ]
            )
        lines.append(
            "- Critical failures: "
            + (", ".join(scorecard.critical_failures) or "none")
        )
        lines.append("")
        turn_by_number = {turn.number: turn for turn in record.turns}
        for turn_number in sorted(referenced_turns):
            lines.extend(_quote(turn_by_number[turn_number]))

    general = [finding for finding in findings if finding.scope == "general"]
    scenario_specific = [
        finding for finding in findings if finding.scope == "scenario-specific"
    ]
    lines.extend([HEADINGS[2], *_finding_lines(general)])
    lines.extend([HEADINGS[3], *_finding_lines(scenario_specific)])
    lines.append(HEADINGS[4])
    infrastructure_records = [
        record
        for record in records
        if record.stop_reason == "infrastructure_failure"
        or record.infrastructure_failure is not None
    ]
    if infrastructure_records:
        lines.extend(
            f"- {record.scenario_id}: {record.infrastructure_failure or 'unspecified'}"
            for record in infrastructure_records
        )
    else:
        lines.append("- None.")

    lines.extend(["", HEADINGS[5], PRIVACY_STATEMENT, "", HEADINGS[6]])
    for record in records:
        disclosure = _validated_disclosure(record.scenario_id, runtime_disclosures)
        user_rules = ", ".join(disclosure.user_home_rule_paths) or "none"
        marker_text = ", ".join(
            f"{marker.marker} ({marker.levels_above_home} "
            f"{'level' if marker.levels_above_home == 1 else 'levels'} above home)"
            for marker in disclosure.above_home_markers
        ) or "none"
        lines.append(
            f"- {record.scenario_id}: user-home rule paths: {user_rules}; "
            f"above-home markers: {marker_text}"
        )
    lines.extend([LIMITATIONS_STATEMENT, ""])

    raw_text = "\n".join(lines)
    text = sanitize_text(raw_text, rules)
    assert_tracked_safe(text, forbidden_literals=tuple(rule.literal for rule in rules))
    validate_baseline_report(text)
    return text


def _require_prefixed(line: str, prefix: str, label: str, *, allow_empty: bool = False) -> str:
    if not line.startswith(prefix):
        raise ValueError(f"baseline report {label} is malformed")
    value = line.removeprefix(prefix)
    if not allow_empty and not value:
        raise ValueError(f"baseline report {label} is empty")
    return value


def _validate_identity_section(lines: list[str]) -> None:
    if lines == ["- No run records.", ""]:
        return
    prefixes = (
        "- Suite ID: ",
        "- Repository commit: ",
        "- Protocol version: ",
        "- Protocol SHA-256: ",
        "- Runtime: ",
        "- Runtime version: ",
        "- Model: ",
    )
    if len(lines) != len(prefixes) + 1 or lines[-1] != "":
        raise ValueError("baseline report evaluation identity is malformed")
    for line, prefix in zip(lines[:-1], prefixes, strict=True):
        _require_prefixed(line, prefix, "evaluation identity")


def _validate_scenario_section(lines: list[str]) -> None:
    if not lines:
        raise ValueError("baseline report scenario results must not be empty")
    index = 0
    while index < len(lines):
        scenario_id = _require_prefixed(lines[index], "### ", "scenario heading")
        if _IDENTIFIER.fullmatch(scenario_id) is None or scenario_id.startswith("Evidence turn "):
            raise ValueError("baseline report scenario heading is malformed")
        index += 1
        if index + 2 >= len(lines):
            raise ValueError("baseline report scenario result is incomplete")
        _require_prefixed(lines[index], "- Run ID: ", "run ID")
        index += 1
        _require_prefixed(lines[index], "- Stop reason: ", "stop reason")
        index += 1

        if lines[index].startswith("- Infrastructure failure: "):
            _require_prefixed(
                lines[index],
                "- Infrastructure failure: ",
                "infrastructure failure",
            )
            index += 1
            if index >= len(lines) or lines[index] != "- Score: not assigned":
                raise ValueError("baseline report infrastructure score is malformed")
            index += 1
            if index >= len(lines) or lines[index] != "":
                raise ValueError("baseline report infrastructure result is malformed")
            index += 1
            continue

        total_match = _TOTAL_LINE.fullmatch(lines[index])
        if total_match is None:
            raise ValueError("baseline report scenario total is malformed")
        total = int(total_match.group(1))
        maximum = int(total_match.group(2))
        index += 1
        if index >= len(lines) or lines[index] != "- Category scores:":
            raise ValueError("baseline report category scores are malformed")
        index += 1

        category_count = 0
        category_total = 0
        referenced_turns: set[int] = set()
        category_ids: set[str] = set()
        while index < len(lines):
            category_match = _CATEGORY_LINE.fullmatch(lines[index])
            if category_match is None:
                break
            category_id = category_match.group(1)
            if category_id in category_ids:
                raise ValueError("baseline report repeats a category")
            category_ids.add(category_id)
            category_count += 1
            category_total += int(category_match.group(2))
            index += 1
            if index + 1 >= len(lines):
                raise ValueError("baseline report category is incomplete")
            _require_prefixed(lines[index], "    - Rationale: ", "category rationale")
            index += 1
            evidence = _require_prefixed(
                lines[index],
                "    - Evidence turns: ",
                "category evidence",
            )
            if _TURN_LIST.fullmatch(evidence) is None:
                raise ValueError("baseline report category evidence is malformed")
            referenced_turns.update(int(turn) for turn in evidence.split(", "))
            index += 1
        if category_count == 0 or total != category_total or maximum != category_count * 2:
            raise ValueError("baseline report scenario score is inconsistent")
        if index >= len(lines):
            raise ValueError("baseline report scenario result is incomplete")
        _require_prefixed(
            lines[index],
            "- Critical failures: ",
            "critical failures",
        )
        index += 1
        if index >= len(lines) or lines[index] != "":
            raise ValueError("baseline report scenario score is malformed")
        index += 1

        quoted_turns: set[int] = set()
        while index < len(lines):
            evidence_match = _EVIDENCE_HEADING.fullmatch(lines[index])
            if evidence_match is None:
                break
            turn = int(evidence_match.group(1))
            if turn in quoted_turns:
                raise ValueError("baseline report repeats an evidence quotation")
            quoted_turns.add(turn)
            index += 1
            if index + 2 >= len(lines):
                raise ValueError("baseline report evidence quotation is incomplete")
            _require_prefixed(lines[index], "> Learner: ", "learner quotation")
            index += 1
            _require_prefixed(lines[index], "> Tutor: ", "tutor quotation")
            index += 1
            if lines[index] != "":
                raise ValueError("baseline report evidence quotation is malformed")
            index += 1
        if quoted_turns != referenced_turns:
            raise ValueError("baseline report quotations do not match score evidence")


def _validate_findings_section(lines: list[str]) -> None:
    if not lines:
        raise ValueError("baseline report findings must not be empty")
    if lines == ["- None.", ""]:
        return
    index = 0
    while index < len(lines):
        identifier = _require_prefixed(lines[index], "### ", "finding heading")
        if _IDENTIFIER.fullmatch(identifier) is None:
            raise ValueError("baseline report finding heading is malformed")
        index += 1
        if index + 5 >= len(lines):
            raise ValueError("baseline report finding is incomplete")
        classification = _require_prefixed(
            lines[index],
            "- Classification: ",
            "finding classification",
        )
        if classification not in _FINDING_CLASSES:
            raise ValueError("baseline report finding classification is invalid")
        index += 1
        _require_prefixed(lines[index], "- Scenarios: ", "finding scenarios")
        index += 1
        _require_prefixed(
            lines[index],
            "- Evidence: ",
            "finding evidence",
            allow_empty=classification != "pedagogy",
        )
        index += 1
        _require_prefixed(lines[index], "- Summary: ", "finding summary")
        index += 1
        _require_prefixed(lines[index], "- Research: ", "finding research")
        index += 1
        if lines[index] != "":
            raise ValueError("baseline report finding is malformed")
        index += 1


def _validate_infrastructure_section(lines: list[str]) -> None:
    if lines == ["- None.", ""]:
        return
    if not lines or lines[-1] != "":
        raise ValueError("baseline report infrastructure section is malformed")
    for line in lines[:-1]:
        value = _require_prefixed(line, "- ", "infrastructure result")
        if ": " not in value or not all(value.split(": ", 1)):
            raise ValueError("baseline report infrastructure result is malformed")


def _validate_limitations_section(lines: list[str]) -> None:
    if not lines or lines[-1] != LIMITATIONS_STATEMENT:
        raise ValueError("baseline report limitations statement is invalid")
    for line in lines[:-1]:
        match = _LIMITATION_LINE.fullmatch(line)
        if match is None:
            raise ValueError("baseline report limitation is malformed")
        user_rules = match.group(2)
        if user_rules != "none" and any(
            rule not in USER_HOME_RULE_PATHS for rule in user_rules.split(", ")
        ):
            raise ValueError("baseline report limitation has an invalid user-home rule")
        markers = match.group(3)
        if markers == "none":
            continue
        for marker_text in markers.split(", "):
            marker_match = _ABOVE_HOME_MARKER.fullmatch(marker_text)
            if marker_match is None or marker_match.group(1) not in RULE_MARKERS:
                raise ValueError("baseline report limitation has an invalid marker")
            levels = int(marker_match.group(2))
            expected_word = "level" if levels == 1 else "levels"
            if marker_match.group(3) != expected_word:
                raise ValueError("baseline report limitation has invalid level grammar")


def validate_baseline_report(text: str) -> None:
    """Reject malformed or unsafe tracked semantic baseline report text."""
    if not isinstance(text, str) or not text.endswith("\n"):
        raise ValueError("baseline report must be newline-terminated text")
    lines = text.splitlines()
    if not lines or lines[0] != TITLE:
        raise ValueError("baseline report title is invalid")
    positions: list[int] = []
    for heading in HEADINGS:
        if lines.count(heading) != 1:
            raise ValueError("baseline report audit sections are invalid")
        positions.append(lines.index(heading))
    if positions != sorted(positions):
        raise ValueError("baseline report audit sections are out of order")
    sections = [
        lines[position + 1 : positions[index + 1]]
        if index + 1 < len(positions)
        else lines[position + 1 :]
        for index, position in enumerate(positions)
    ]
    _validate_identity_section(sections[0])
    _validate_scenario_section(sections[1])
    _validate_findings_section(sections[2])
    _validate_findings_section(sections[3])
    _validate_infrastructure_section(sections[4])
    if sections[5] != [PRIVACY_STATEMENT, ""]:
        raise ValueError("baseline report privacy statement is invalid")
    _validate_limitations_section(sections[6])
    for line in lines:
        if line.startswith("> Learner: ") and len(line.removeprefix("> Learner: ")) > 600:
            raise ValueError("baseline report contains an overlong learner quotation")
        if line.startswith("> Tutor: ") and len(line.removeprefix("> Tutor: ")) > 600:
            raise ValueError("baseline report contains an overlong tutor quotation")
    assert_tracked_safe(text, forbidden_literals=())


def write_sanitized_report(path: Path, text: str) -> Path:
    """Validate and atomically write one UTF-8 tracked report."""
    validate_baseline_report(text)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=destination.parent,
        prefix=".semantic-report-",
    )
    committed = False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        committed = True
    finally:
        if not committed:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    return destination
