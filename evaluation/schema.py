"""Strict, immutable schemas and loaders for semantic evaluation fixtures."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Literal, NoReturn

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
StopReason = Literal[
    "observable_outcome",
    "maximum_learner_responses",
    "completion_without_evidence",
    "critical_pedagogical_failure",
    "infrastructure_failure",
]
FindingClass = Literal[
    "pedagogy",
    "launcher_ux",
    "documentation",
    "runtime",
    "infrastructure",
]

SCHEMA_VERSION = 1
SCENARIO_SCHEMA_V1 = 1
SCENARIO_SCHEMA_V2 = 2
RUN_SCHEMA_V1 = 1
RUN_SCHEMA_V2 = 2
RUN_WRITE_SCHEMA_VERSION = RUN_SCHEMA_V2
SUITE_SCHEMA_VERSION = 1
MAX_LEARNER_RESPONSES = 15
KNOWN_REPORT_CONTRACTS = frozenset({"baseline-v1", "article-reading-v1"})
RESERVED_SCENARIO_IDS = frozenset({"article-reading"})

_STOP_REASONS = frozenset(
    {
        "observable_outcome",
        "maximum_learner_responses",
        "completion_without_evidence",
        "critical_pedagogical_failure",
        "infrastructure_failure",
    }
)
_DOMAINS = frozenset({"conceptual", "procedural", "communication"})
_IDENTIFIER = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class Scenario:
    schema_version: int
    identifier: str
    title: str
    domain: Literal["conceptual", "procedural", "communication"]
    initial_goal: str
    persona: Mapping[str, tuple[str, ...] | str]
    observable_outcome: tuple[str, ...]
    response_policy: tuple[str, ...]
    max_learner_responses: int
    source_fixture_id: str | None = None


@dataclass(frozen=True)
class RubricCategory:
    identifier: str
    label: str
    anchors: Mapping[int, str]


@dataclass(frozen=True)
class Rubric:
    schema_version: int
    allowed_scores: tuple[int, ...]
    categories: tuple[RubricCategory, ...]
    critical_failures: tuple[str, ...]
    infrastructure_failures: tuple[str, ...]

    @property
    def maximum_score(self) -> int:
        return len(self.categories) * max(self.allowed_scores)


@dataclass(frozen=True)
class StreamContract:
    schema_version: int
    antigravity_version: str
    model_identifier: str
    request_text_pointer: str
    output_text_pointers: tuple[str, ...]
    completion_pointer: str
    completion_value: JsonValue
    request_template: dict[str, JsonValue]
    sample_output_events: tuple[dict[str, JsonValue], ...]


@dataclass(frozen=True)
class TurnRecord:
    number: int
    learner: str
    tutor: str


@dataclass(frozen=True)
class RunRecord:
    schema_version: int
    run_id: str
    suite_id: str
    scenario_id: str
    repository_commit: str
    protocol_version: str
    protocol_sha256: str
    runtime: Literal["antigravity"]
    runtime_version: str
    model_identifier: str
    learner_response_count: int
    stop_reason: StopReason
    infrastructure_failure: str | None
    turns: tuple[TurnRecord, ...]
    scenario_sha256: str | None = None
    rubric_sha256: str | None = None
    suite_sha256: str | None = None


@dataclass(frozen=True)
class FixtureIdentities:
    scenario_sha256: str
    rubric_sha256: str
    suite_sha256: str


@dataclass(frozen=True)
class SuiteManifest:
    schema_version: int
    identifier: str
    scenario_ids: tuple[str, ...]
    rubric_path: str
    report_contract: str


@dataclass(frozen=True)
class CategoryScore:
    identifier: str
    score: Literal[0, 1, 2]
    evidence_turns: tuple[int, ...]
    rationale: str


@dataclass(frozen=True)
class Scorecard:
    schema_version: int
    scenario_id: str
    categories: tuple[CategoryScore, ...]
    critical_failures: tuple[str, ...]

    @property
    def total(self) -> int:
        return sum(category.score for category in self.categories)


@dataclass(frozen=True)
class Finding:
    identifier: str
    classification: FindingClass
    scope: Literal["general", "scenario-specific"]
    scenario_ids: tuple[str, ...]
    evidence_turns: tuple[str, ...]
    summary: str
    research_links: tuple[str, ...]


def fixture_root() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def fixture_sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if not _SHA256.fullmatch(digest):
        _fail("fixture hash must be 64 lowercase hexadecimal characters")
    return digest


def known_scenario_ids() -> frozenset[str]:
    scenario_root = fixture_root() / "scenarios"
    discovered = {
        path.stem
        for path in scenario_root.glob("*.json")
        if path.is_file()
    }
    return frozenset(discovered | RESERVED_SCENARIO_IDS)


def resolve_fixture_path(relative: str, *, label: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        _fail(f"{label} must be a non-empty relative POSIX path")
    if "\\" in relative or relative.startswith("/") or PurePosixPath(relative).is_absolute():
        _fail(f"{label} must be a canonical relative POSIX path")
    if any(part in {".", ".."} for part in PurePosixPath(relative).parts):
        _fail(f"{label} must not contain path traversal")
    root = fixture_root().resolve(strict=False)
    candidate = (root / relative).resolve(strict=False)
    if not _contains_fixture_root(root, candidate):
        _fail(f"{label} must resolve under the evaluation fixture root")
    return candidate


def _contains_fixture_root(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def suite_manifest_path(identifier: str) -> Path:
    return fixture_root() / "suites" / f"{identifier}.json"


def load_suite_manifest(path: Path) -> SuiteManifest:
    label = "suite manifest"
    document = _load_object(path, label)
    _require_keys(
        document,
        {
            "schema_version",
            "identifier",
            "scenario_ids",
            "rubric_path",
            "report_contract",
        },
        label,
    )
    version = _integer(document["schema_version"], f"{label}.schema_version")
    if version != SUITE_SCHEMA_VERSION:
        _fail(f"{label}.schema_version must be {SUITE_SCHEMA_VERSION}")
    identifier = _identifier(document["identifier"], f"{label}.identifier")
    scenario_ids = _identifier_array(document["scenario_ids"], f"{label}.scenario_ids")
    if not scenario_ids:
        _fail(f"{label}.scenario_ids must not be empty")
    known = known_scenario_ids()
    if any(scenario_id not in known for scenario_id in scenario_ids):
        _fail(f"{label}.scenario_ids contains an unknown scenario")
    rubric_path = _string(document["rubric_path"], f"{label}.rubric_path")
    resolve_fixture_path(rubric_path, label=f"{label}.rubric_path")
    report_contract = _identifier(
        document["report_contract"],
        f"{label}.report_contract",
    )
    if report_contract not in KNOWN_REPORT_CONTRACTS:
        _fail(f"{label}.report_contract must be a known report contract")
    return SuiteManifest(
        schema_version=SUITE_SCHEMA_VERSION,
        identifier=identifier,
        scenario_ids=scenario_ids,
        rubric_path=rubric_path,
        report_contract=report_contract,
    )


def scenario_fixture_sha256(scenario_id: str) -> str:
    scenario_path = fixture_root() / "scenarios" / f"{scenario_id}.json"
    if scenario_id in RESERVED_SCENARIO_IDS and not scenario_path.is_file():
        _fail("reserved scenario fixture is not yet available")
    if not scenario_path.is_file():
        _fail("scenario fixture is unavailable")
    return fixture_sha256(scenario_path)


def identities_for_scenario(
    manifest: SuiteManifest,
    scenario_id: str,
) -> FixtureIdentities:
    if scenario_id not in manifest.scenario_ids:
        _fail("scenario is not part of the selected suite manifest")
    rubric = resolve_fixture_path(manifest.rubric_path, label="suite manifest rubric_path")
    return FixtureIdentities(
        scenario_sha256=scenario_fixture_sha256(scenario_id),
        rubric_sha256=fixture_sha256(rubric),
        suite_sha256=fixture_sha256(suite_manifest_path(manifest.identifier)),
    )


def manifest_fixture_identities(manifest: SuiteManifest) -> tuple[str, str, tuple[str, ...]]:
    rubric = resolve_fixture_path(manifest.rubric_path, label="suite manifest rubric_path")
    return (
        fixture_sha256(suite_manifest_path(manifest.identifier)),
        fixture_sha256(rubric),
        tuple(scenario_fixture_sha256(scenario_id) for scenario_id in manifest.scenario_ids),
    )


def load_scenario(path: Path) -> Scenario:
    label = "scenario"
    document = _load_object(path, label)
    version = _integer(document["schema_version"], f"{label}.schema_version")
    base_keys = {
        "schema_version",
        "identifier",
        "title",
        "domain",
        "initial_goal",
        "persona",
        "observable_outcome",
        "response_policy",
        "max_learner_responses",
    }
    if version == SCENARIO_SCHEMA_V1:
        expected = base_keys
    elif version == SCENARIO_SCHEMA_V2:
        expected = base_keys | {"source_fixture_id"}
    else:
        _fail(f"{label}.schema_version must be {SCENARIO_SCHEMA_V1} or {SCENARIO_SCHEMA_V2}")
    _require_keys(document, expected, label)
    domain = _string(document["domain"], f"{label}.domain")
    if domain not in _DOMAINS:
        _fail(f"{label}.domain must be one of {sorted(_DOMAINS)}, got {domain!r}")
    max_responses = _integer(document["max_learner_responses"], f"{label}.max_learner_responses")
    if max_responses != MAX_LEARNER_RESPONSES:
        _fail(f"{label}.max_learner_responses must be {MAX_LEARNER_RESPONSES}")
    source_fixture_id: str | None = None
    if version == SCENARIO_SCHEMA_V2:
        raw_source = document["source_fixture_id"]
        if raw_source is None:
            source_fixture_id = None
        else:
            source_fixture_id = _identifier(
                raw_source,
                f"{label}.source_fixture_id",
            )
    return Scenario(
        schema_version=version,
        identifier=_identifier(document["identifier"], f"{label}.identifier"),
        title=_string(document["title"], f"{label}.title"),
        domain=domain,  # type: ignore[arg-type]
        initial_goal=_string(document["initial_goal"], f"{label}.initial_goal"),
        persona=_persona(document["persona"], f"{label}.persona"),
        observable_outcome=_string_array(
            document["observable_outcome"], f"{label}.observable_outcome"
        ),
        response_policy=_string_array(document["response_policy"], f"{label}.response_policy"),
        max_learner_responses=max_responses,
        source_fixture_id=source_fixture_id,
    )


def load_rubric(path: Path) -> Rubric:
    label = "rubric"
    document = _load_object(path, label)
    _require_keys(
        document,
        {
            "schema_version",
            "allowed_scores",
            "categories",
            "critical_failures",
            "infrastructure_failures",
        },
        label,
    )
    _require_schema_version(document, label)
    scores = _array(document["allowed_scores"], f"{label}.allowed_scores")
    allowed_scores = tuple(
        _integer(score, f"{label}.allowed_scores[{index}]") for index, score in enumerate(scores)
    )
    if not allowed_scores or allowed_scores[0] < 0:
        _fail(f"{label}.allowed_scores must be non-empty and non-negative")
    if list(allowed_scores) != sorted(set(allowed_scores)):
        _fail(f"{label}.allowed_scores must be unique and ascending")

    raw_categories = _array(document["categories"], f"{label}.categories")
    if not raw_categories:
        _fail(f"{label}.categories must not be empty")
    categories = tuple(
        _rubric_category(item, f"{label}.categories[{index}]", allowed_scores)
        for index, item in enumerate(raw_categories)
    )
    _require_unique([category.identifier for category in categories], f"{label}.categories")
    critical = _identifier_array(document["critical_failures"], f"{label}.critical_failures")
    infrastructure = _identifier_array(
        document["infrastructure_failures"], f"{label}.infrastructure_failures"
    )
    return Rubric(
        schema_version=SCHEMA_VERSION,
        allowed_scores=allowed_scores,
        categories=categories,
        critical_failures=critical,
        infrastructure_failures=infrastructure,
    )


def load_stream_contract(path: Path) -> StreamContract:
    label = "stream contract"
    document = _load_object(path, label)
    _require_keys(
        document,
        {
            "schema_version",
            "antigravity_version",
            "model_identifier",
            "request_text_pointer",
            "output_text_pointers",
            "completion_pointer",
            "completion_value",
            "request_template",
            "sample_output_events",
        },
        label,
    )
    _require_schema_version(document, label)
    pointers = _array(document["output_text_pointers"], f"{label}.output_text_pointers")
    if not pointers:
        _fail(f"{label}.output_text_pointers must not be empty")
    events = _array(document["sample_output_events"], f"{label}.sample_output_events")
    return StreamContract(
        schema_version=SCHEMA_VERSION,
        antigravity_version=_string(document["antigravity_version"], f"{label}.antigravity_version"),
        model_identifier=_string(document["model_identifier"], f"{label}.model_identifier"),
        request_text_pointer=_json_pointer(
            document["request_text_pointer"], f"{label}.request_text_pointer"
        ),
        output_text_pointers=tuple(
            _json_pointer(pointer, f"{label}.output_text_pointers[{index}]")
            for index, pointer in enumerate(pointers)
        ),
        completion_pointer=_json_pointer(
            document["completion_pointer"], f"{label}.completion_pointer"
        ),
        completion_value=document["completion_value"],
        request_template=_object(document["request_template"], f"{label}.request_template"),
        sample_output_events=tuple(
            _object(event, f"{label}.sample_output_events[{index}]")
            for index, event in enumerate(events)
        ),
    )


def load_run_record(path: Path) -> RunRecord:
    label = "run record"
    document = _load_object(path, label)
    version = _integer(document["schema_version"], f"{label}.schema_version")
    base_keys = {
        "schema_version",
        "run_id",
        "suite_id",
        "scenario_id",
        "repository_commit",
        "protocol_version",
        "protocol_sha256",
        "runtime",
        "runtime_version",
        "model_identifier",
        "learner_response_count",
        "stop_reason",
        "infrastructure_failure",
        "turns",
    }
    if version == RUN_SCHEMA_V1:
        expected = base_keys
    elif version == RUN_SCHEMA_V2:
        expected = base_keys | {
            "scenario_sha256",
            "rubric_sha256",
            "suite_sha256",
        }
    else:
        _fail(f"{label}.schema_version must be {RUN_SCHEMA_V1} or {RUN_SCHEMA_V2}")
    _require_keys(document, expected, label)
    runtime = _string(document["runtime"], f"{label}.runtime")
    if runtime != "antigravity":
        _fail(f"{label}.runtime must be 'antigravity', got {runtime!r}")
    protocol_sha256 = _sha256_field(document["protocol_sha256"], f"{label}.protocol_sha256")
    count = _integer(document["learner_response_count"], f"{label}.learner_response_count")
    if not 0 <= count <= MAX_LEARNER_RESPONSES:
        _fail(
            f"{label}.learner_response_count must be between 0 and "
            f"{MAX_LEARNER_RESPONSES}"
        )
    stop_reason = _string(document["stop_reason"], f"{label}.stop_reason")
    if stop_reason not in _STOP_REASONS:
        _fail(f"{label}.stop_reason must be one of {sorted(_STOP_REASONS)}, got {stop_reason!r}")
    failure = document["infrastructure_failure"]
    if failure is not None:
        failure = _string(failure, f"{label}.infrastructure_failure")
    turns = _array(document["turns"], f"{label}.turns")
    scenario_sha256: str | None = None
    rubric_sha256: str | None = None
    suite_sha256: str | None = None
    if version == RUN_SCHEMA_V2:
        scenario_sha256 = _sha256_field(
            document["scenario_sha256"],
            f"{label}.scenario_sha256",
        )
        rubric_sha256 = _sha256_field(
            document["rubric_sha256"],
            f"{label}.rubric_sha256",
        )
        suite_sha256 = _sha256_field(
            document["suite_sha256"],
            f"{label}.suite_sha256",
        )
    record = RunRecord(
        schema_version=version,
        run_id=_string(document["run_id"], f"{label}.run_id"),
        suite_id=_string(document["suite_id"], f"{label}.suite_id"),
        scenario_id=_identifier(document["scenario_id"], f"{label}.scenario_id"),
        repository_commit=_string(document["repository_commit"], f"{label}.repository_commit"),
        protocol_version=_string(document["protocol_version"], f"{label}.protocol_version"),
        protocol_sha256=protocol_sha256,
        runtime="antigravity",
        runtime_version=_string(document["runtime_version"], f"{label}.runtime_version"),
        model_identifier=_string(document["model_identifier"], f"{label}.model_identifier"),
        learner_response_count=count,
        stop_reason=stop_reason,  # type: ignore[arg-type]
        infrastructure_failure=failure,
        turns=tuple(_turn(item, f"{label}.turns[{index}]") for index, item in enumerate(turns)),
        scenario_sha256=scenario_sha256,
        rubric_sha256=rubric_sha256,
        suite_sha256=suite_sha256,
    )
    validate_run_record(record)
    return record


def validate_run_record(record: RunRecord, rubric: Rubric | None = None) -> None:
    """Validate cross-field run invariants, plus rubric classes when available."""
    if not 0 <= record.learner_response_count <= MAX_LEARNER_RESPONSES:
        _fail(
            "run record learner_response_count must be between 0 and "
            f"{MAX_LEARNER_RESPONSES}"
        )
    is_infrastructure = record.stop_reason == "infrastructure_failure"
    if is_infrastructure != (record.infrastructure_failure is not None):
        _fail(
            "run record infrastructure_failure must be present iff "
            "stop_reason is infrastructure_failure"
        )
    if (
        rubric is not None
        and record.infrastructure_failure is not None
        and record.infrastructure_failure not in rubric.infrastructure_failures
    ):
        _fail("run record contains an unknown infrastructure failure")

    numbers = [turn.number for turn in record.turns]
    if numbers != list(range(1, len(numbers) + 1)):
        _fail("run record turn numbers must be unique and sequential")
    expected_responses = max(0, len(record.turns) - 1)
    if record.learner_response_count != expected_responses:
        _fail(
            "run record learner_response_count must match recorded turns "
            "after the bootstrap turn"
        )


def _fail(message: str) -> NoReturn:
    raise ValueError(message)


def _reject_constant(name: str) -> NoReturn:
    _fail(f"non-finite JSON number is not allowed: {name}")


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _load_object(path: Path, label: str) -> dict[str, JsonValue]:
    text = Path(path).read_text(encoding="utf-8")
    try:
        document = json.loads(
            text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant
        )
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} is not valid JSON: {error}") from error
    return _object(document, label)


def _object(value: object, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    return value


def _array(value: object, label: str) -> list[JsonValue]:
    if not isinstance(value, list):
        _fail(f"{label} must be an array")
    return value


def _require_keys(document: Mapping[str, object], expected: Collection[str], label: str) -> None:
    actual = set(document)
    missing = sorted(set(expected) - actual)
    unexpected = sorted(actual - set(expected))
    if missing:
        _fail(f"{label} is missing required keys: {missing}")
    if unexpected:
        _fail(f"{label} has unexpected keys: {unexpected}")


def _require_schema_version(document: Mapping[str, object], label: str) -> None:
    if _integer(document["schema_version"], f"{label}.schema_version") != SCHEMA_VERSION:
        _fail(f"{label}.schema_version must be {SCHEMA_VERSION}")


def _sha256_field(value: object, label: str) -> str:
    text = _string(value, label)
    if not _SHA256.fullmatch(text):
        _fail(f"{label} must be 64 lowercase hexadecimal characters")
    return text


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{label} must be an integer")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label} must be a non-empty string")
    return value


def _identifier(value: object, label: str) -> str:
    text = _string(value, label)
    if not _IDENTIFIER.fullmatch(text):
        _fail(f"{label} must be a lowercase hyphenated identifier, got {text!r}")
    return text


def _require_unique(values: list[str], label: str) -> None:
    if len(set(values)) != len(values):
        _fail(f"{label} must not contain duplicates")


def _string_array(value: object, label: str) -> tuple[str, ...]:
    items = _array(value, label)
    if not items:
        _fail(f"{label} must not be empty")
    return tuple(_string(item, f"{label}[{index}]") for index, item in enumerate(items))


def _identifier_array(value: object, label: str) -> tuple[str, ...]:
    items = _array(value, label)
    if not items:
        _fail(f"{label} must not be empty")
    identifiers = tuple(
        _identifier(item, f"{label}[{index}]") for index, item in enumerate(items)
    )
    _require_unique(list(identifiers), label)
    return identifiers


def _json_pointer(value: object, label: str) -> str:
    if not isinstance(value, str) or (value and not value.startswith("/")):
        _fail(f"{label} must be a JSON Pointer (empty or starting with '/')")
    return value


_PERSONA_TEXT_KEYS = frozenset({"misconception"})
_PERSONA_LIST_KEYS = frozenset(
    {"knowledge", "communication_style", "allowed_progress", "forbidden_behavior"}
)


def _persona(value: object, label: str) -> Mapping[str, tuple[str, ...] | str]:
    persona = _object(value, label)
    _require_keys(persona, _PERSONA_TEXT_KEYS | _PERSONA_LIST_KEYS, label)
    parsed: dict[str, tuple[str, ...] | str] = {}
    for key in sorted(persona):
        if key in _PERSONA_TEXT_KEYS:
            parsed[key] = _string(persona[key], f"{label}.{key}")
        else:
            parsed[key] = _string_array(persona[key], f"{label}.{key}")
    return MappingProxyType(parsed)


def _rubric_category(value: object, label: str, allowed_scores: tuple[int, ...]) -> RubricCategory:
    category = _object(value, label)
    _require_keys(category, {"identifier", "label", "anchors"}, label)
    raw_anchors = _object(category["anchors"], f"{label}.anchors")
    expected = {str(score) for score in allowed_scores}
    _require_keys(raw_anchors, expected, f"{label}.anchors")
    anchors = {
        score: _string(raw_anchors[str(score)], f"{label}.anchors[{score}]")
        for score in allowed_scores
    }
    return RubricCategory(
        identifier=_identifier(category["identifier"], f"{label}.identifier"),
        label=_string(category["label"], f"{label}.label"),
        anchors=MappingProxyType(anchors),
    )


def _turn(value: object, label: str) -> TurnRecord:
    turn = _object(value, label)
    _require_keys(turn, {"number", "learner", "tutor"}, label)
    number = _integer(turn["number"], f"{label}.number")
    if number < 1:
        _fail(f"{label}.number must be positive")
    return TurnRecord(
        number=number,
        learner=_string(turn["learner"], f"{label}.learner"),
        tutor=_string(turn["tutor"], f"{label}.tutor"),
    )
