"""Behavioral conformance checks for the universal tutor prompt."""

from __future__ import annotations

import re
from dataclasses import dataclass


CONFORMANCE_CONTRACT_VERSION = 1


@dataclass(frozen=True)
class Diagnostic:
    """One stable, actionable behavioral contract failure."""

    code: str
    path: str
    message: str
    remediation: str


@dataclass(frozen=True)
class _Contract:
    code: str
    path: str
    marker_groups: tuple[tuple[str, ...], ...]
    message: str
    remediation: str


_CONTRACTS = (
    _Contract(
        "active-return-after-exposition",
        "core/pedagogy.md",
        (
            (
                "after exposition, return control",
                "after direct exposition, return control",
            ),
            ("active application", "active question", "active work"),
        ),
        "exposition does not return control to the learner through active work",
        "state that exposition is followed by an active application or question",
    ),
    _Contract(
        "bounded-diagnosis",
        "core/assessment.md",
        (
            (
                "at most six diagnostic questions",
                "default budget is six questions",
                "diagnostic budget is six questions",
            ),
            ("stop early", "stop before the budget"),
        ),
        "diagnosis has no explicit default bound and early-stop rule",
        "set a default diagnostic question budget and stop when evidence is sufficient",
    ),
    _Contract(
        "capability-fallbacks",
        "core/session-protocol.md",
        (
            ("capability fallbacks", "capability fallback"),
            ("without structured quiz", "structured quiz support"),
            ("without web access", "web access"),
            ("without filesystem access", "filesystem access"),
            (
                "without subagents",
                "without parallel work",
                "without parallelism",
                "subagents unavailable",
                "parallelism unavailable",
            ),
            (
                "without diagram rendering",
                "without rendering support",
                "diagram rendering unavailable",
            ),
            (
                "without cross-session memory",
                "cross-session memory unavailable",
                "without memory support",
            ),
        ),
        "required capability fallbacks are incomplete",
        "restore explicit quiz, web, filesystem, subagent/parallelism, "
        "diagram/rendering, and cross-session-memory fallback behavior",
    ),
    _Contract(
        "evidence-based-closure",
        "core/session-protocol.md",
        (
            ("close with", "close and persist"),
            ("diagnostic evidence",),
            ("application evidence",),
            ("remaining gaps",),
        ),
        "session closure does not require evidence and remaining gaps",
        "require diagnostic evidence, application evidence, and remaining gaps at closure",
    ),
    _Contract(
        "exposition-fallback",
        "core/pedagogy.md",
        (
            ("direct exposition",),
            ("not deducible", "cannot be deduced", "inappropriate cognitive load"),
        ),
        "direct exposition is not available when discovery is unsuitable",
        "restore direct exposition for non-deducible information or excessive cognitive load",
    ),
    _Contract(
        "mathematical-assumptions-classification",
        "core/evidence-policy.md",
        (
            ("domain and hypotheses", "domain, assumptions, and hypotheses"),
            ("classify", "classification"),
            ("definition",),
            ("theorem",),
            ("approximation",),
        ),
        "mathematical claims lack assumptions or classification requirements",
        "require domains and hypotheses plus explicit mathematical claim classification",
    ),
    _Contract(
        "observable-outcome",
        "core/session-protocol.md",
        (
            ("observable outcome", "performance that can be observed"),
            ("performance that can be observed", "observable performance"),
        ),
        "the session protocol does not establish an observable learner outcome",
        "restore an observable performance and its completion evidence",
    ),
    _Contract(
        "private-state",
        "core/session-protocol.md",
        (
            ("workspace/", "workspace"),
            ("out of version control", "never add them to version control"),
        ),
        "private learner state is not kept out of version control",
        "keep learner state under workspace/ and explicitly exclude it from version control",
    ),
    _Contract(
        "responsive-socratic-follow-up",
        "core/pedagogy.md",
        (
            ("socratic",),
            (
                "derives from the learner's preceding answer",
                "derive from the learner's preceding answer",
                "actual reasoning before choosing the next probe",
            ),
        ),
        "Socratic follow-up is not tied to the learner's preceding response",
        "make each next probe respond to the learner's actual prior reasoning",
    ),
    _Contract(
        "volatile-primary-source-verification",
        "core/evidence-policy.md",
        (
            ("volatile",),
            ("verify",),
            ("primary source",),
        ),
        "volatile technical claims do not require primary-source verification",
        "require consequential volatile claims to be checked against primary sources",
    ),
)

_APPROVAL_CODE = "plan-approval-before-teaching"
REQUIRED_DIAGNOSTIC_CODES = tuple(
    sorted((*(_contract.code for _contract in _CONTRACTS), _APPROVAL_CODE))
)

_SOURCE_RE = re.compile(
    r"<!-- source:(?P<path>[^>]+) -->(?P<body>.*?)"
    r"<!-- /source:(?P=path) -->",
    re.DOTALL,
)


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def _source_sections(bundle: str) -> dict[str, str]:
    return {
        match.group("path"): _normalize(match.group("body"))
        for match in _SOURCE_RE.finditer(bundle)
    }


def _has_groups(text: str, groups: tuple[tuple[str, ...], ...]) -> bool:
    return all(any(_normalize(marker) in text for marker in group) for group in groups)


def _approval_diagnostic(protocol: str) -> Diagnostic | None:
    approval_section_markers = (
        "present and approve a dependency path",
        "approve a dependency path",
    )
    approval_gate_markers = (
        "learner approves or adjusts the path",
        "learner approves the path",
        "learner approval before teaching",
    )
    teaching_section_markers = ("teach one node at a time", "teaching phase")
    approval_section_indexes = [
        protocol.find(_normalize(marker))
        for marker in approval_section_markers
        if protocol.find(_normalize(marker)) >= 0
    ]
    approval_gate_indexes = [
        protocol.find(_normalize(marker))
        for marker in approval_gate_markers
        if protocol.find(_normalize(marker)) >= 0
    ]
    teaching_section_indexes = [
        protocol.find(_normalize(marker))
        for marker in teaching_section_markers
        if protocol.find(_normalize(marker)) >= 0
    ]
    if (
        approval_section_indexes
        and approval_gate_indexes
        and teaching_section_indexes
        and min(approval_section_indexes)
        < min(approval_gate_indexes)
        < min(teaching_section_indexes)
    ):
        return None
    return Diagnostic(
        _APPROVAL_CODE,
        "core/session-protocol.md",
        "teaching is not gated by prior learner approval of the dependency path",
        "place explicit learner path approval before the teaching phase",
    )


def check_conformance(bundle: str) -> list[Diagnostic]:
    """Return every behavioral contract failure in deterministic order."""

    sections = _source_sections(bundle)
    diagnostics = []
    for contract in _CONTRACTS:
        section = sections.get(contract.path, "")
        if not _has_groups(section, contract.marker_groups):
            diagnostics.append(
                Diagnostic(
                    contract.code,
                    contract.path,
                    contract.message,
                    contract.remediation,
                )
            )

    approval = _approval_diagnostic(sections.get("core/session-protocol.md", ""))
    if approval is not None:
        diagnostics.append(approval)
    return sorted(diagnostics, key=lambda item: (item.code, item.path))
