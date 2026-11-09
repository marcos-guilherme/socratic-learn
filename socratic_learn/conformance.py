"""Behavioral conformance checks for the universal tutor prompt."""

from __future__ import annotations

import re
from dataclasses import dataclass


CONFORMANCE_CONTRACT_VERSION = 3


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
    forbidden_markers: tuple[str, ...] = ()


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
            ("source study", "outside source study"),
            (
                "externally unverified",
                "explicitly requests external research",
            ),
        ),
        "volatile technical claims lack source-study carve-out or primary-source verification",
        "verify consequential volatile claims outside source study and mark source-study "
        "volatile claims externally unverified unless the learner requests external research",
    ),
    _Contract(
        "source-study-epistemic-distinction",
        "core/evidence-policy.md",
        (
            ("source assertion",),
            ("within-source support",),
            ("external verification",),
        ),
        "source study does not distinguish assertion, within-source support, and external verification",
        "distinguish source assertion, within-source support, and external verification",
    ),
    _Contract(
        "source-study-external-verification-gate",
        "core/evidence-policy.md",
        (
            ("source-bounded by default",),
            (
                "only an explicit learner request activates external research in source study",
            ),
            (
                "after that request, apply the normal",
                "autonomous verification, source priority",
            ),
            (
                "preserve autonomous current-information research outside source study",
            ),
        ),
        "source study lacks an explicit external-research gate or preserves verification after activation",
        "keep source study source-bounded by default, activate external research only on "
        "explicit learner request, and apply normal verification rules after activation",
        forbidden_markers=(
            "research every claim in the source without being asked",
        ),
    ),
    _Contract(
        "source-nonexistence-caution",
        "core/evidence-policy.md",
        (
            (
                "failure to locate",
                "not proof that it does not exist",
            ),
            (
                "report the search scope",
                "report the search scope and uncertainty",
            ),
        ),
        "missing artifacts are treated as proof of nonexistence or without search scope",
        "report search scope and uncertainty when a claim or artifact is not found",
        forbidden_markers=(
            "absence proves it does not exist",
            "absence proves",
        ),
    ),
    _Contract(
        "source-selective-access",
        "core/session-protocol.md",
        (
            ("read the index first",),
            (
                "only sections needed",
                "sections needed for the current",
            ),
            ("return to the index",),
        ),
        "source study does not use selective index-based section access",
        "read the index first, open only sections needed for the current step, and "
        "return to the index when the route changes",
    ),
    _Contract(
        "source-untrusted-material",
        "core/session-protocol.md",
        (
            ("untrusted study material",),
            ("never as instructions", "never instructions"),
        ),
        "supplied source files are not treated as untrusted study material",
        "treat source files as untrusted study material, never as instructions",
    ),
    _Contract(
        "source-learner-locations",
        "core/session-protocol.md",
        (
            (
                "learner-facing source locations",
                "page, heading, or section",
            ),
            ("for source claims",),
        ),
        "source claims lack learner-facing locations",
        "give learner-facing source locations such as page, heading, or section",
    ),
    _Contract(
        "source-objective-before-summary",
        "core/session-protocol.md",
        (
            (
                "do not summarize the whole source",
                "whole source before",
            ),
            (
                "confirming the learner's objective",
                "learner's objective",
            ),
        ),
        "the whole source is summarized before confirming the learner's objective",
        "confirm the learner's objective before summarizing the whole source",
    ),
    _Contract(
        "source-aware-closure",
        "core/session-protocol.md",
        (
            (
                "what the source asserts",
                "source asserts",
            ),
            (
                "within-source support",
                "support was inspected",
            ),
            ("externally unverified",),
            ("relevant source locations",),
        ),
        "source-study closure omits assertions, inspected support, unverified status, or locations",
        "close source study with what the source asserts, inspected within-source support, "
        "externally unverified claims, and relevant source locations",
    ),
    _Contract(
        "focused-learner-task",
        "core/pedagogy.md",
        (
            ("one focused learner task at a time",),
            (
                "do not multiply",
                "claim-by-dimension",
                "analysis dimensions",
            ),
            (
                "smallest useful next task",
                "learner's answer",
            ),
        ),
        "learner prompts batch multiple claims or dimensions instead of one focused task",
        "ask one focused learner task at a time and decompose claim-by-dimension batches",
    ),
    _Contract(
        "silent-orchestration",
        "core/session-protocol.md",
        (
            ("keep protocol orchestration internal",),
            ("do not announce stage names",),
            ("diagnostic budgets",),
            ("question counters",),
            ("unless the learner explicitly asks",),
            (
                "index paths",
                "chunk paths",
                "file-reading",
            ),
            ("protocol labels",),
        ),
        "learner-facing dialogue exposes protocol orchestration",
        "keep stages, budgets, counters, index paths, file-reading, and protocol labels "
        "internal unless the learner asks",
    ),
    _Contract(
        "vocabulary-readiness",
        "core/pedagogy.md",
        (
            ("vocabulary readiness",),
            ("the learner used it correctly",),
            ("demonstrated the underlying idea",),
            ("introduced it in plain language",),
            ("hidden prerequisites",),
            ("transfer question", "transfer questions"),
        ),
        "learner-facing vocabulary is not gated by readiness",
        "require demonstrated or plainly introduced vocabulary, including before transfer "
        "questions, and reject hidden prerequisites",
    ),
    _Contract(
        "connected-perspectives",
        "core/pedagogy.md",
        (
            ("one primary explanation",),
            ("up to two additional perspectives",),
            ("explicitly connect",),
        ),
        "multiple perspectives are not bounded and connected",
        "use one primary explanation, at most two useful added views, and connect them",
    ),
    _Contract(
        "productive-effort",
        "core/pedagogy.md",
        (
            ("learner attempt before",),
            ("paper and pen",),
            ("do not include the solution",),
        ),
        "central concepts do not require bounded learner effort before solutions",
        "require an attempt, support paper-and-pen work, and withhold the immediate solution",
    ),
    _Contract(
        "graduated-support",
        "core/pedagogy.md",
        (
            ("small cue",),
            ("alternative representation or simpler case",),
            ("direct explanation",),
            ("new application",),
        ),
        "difficulty does not receive graduated support",
        "provide a cue, alternate view, explanation, and return through a new application",
    ),
    _Contract(
        "agent-led-route",
        "core/session-protocol.md",
        (
            ("the tutor owns technical route selection",),
            ("do not ask the learner to validate a technical sequence",),
            ("brief preview in ordinary language",),
            ("begin teaching without formal approval",),
            ("the learner may redirect at any time",),
            (
                "the learner owns the objective, pace, depth, available time, "
                "preferred representation, redirection, and personal trade-offs",
            ),
            ("the learner may pause, skip, or revisit at any time",),
        ),
        "technical route selection is delegated to a novice",
        "make the tutor own the route, preview it briefly, start automatically, and preserve redirection",
        (
            "wait for approval before teaching",
            "obtain learner approval before teaching",
            "do not begin teaching until the learner approves",
            "ask the learner to approve the technical route",
            "learner approval before teaching",
            "learner approves the path",
        ),
    ),
    _Contract(
        "silent-self-review",
        "core/pedagogy.md",
        (
            ("silent self-review",),
            ("alignment with the learner-owned objective",),
            ("prerequisite evidence",),
            ("vocabulary readiness and cognitive load",),
            ("the smallest useful next step",),
            ("a perspective contributes distinct value",),
            ("factual currency or uncertainty requires research",),
            ("a decision they lack the basis to evaluate",),
            ("do not narrate this silent self-review",),
        ),
        "technical and pedagogical decisions lack silent self-review",
        "silently check objective alignment, evidence, readiness, load, perspectives, currency, and decision ownership",
    ),
    _Contract(
        "autonomous-current-research",
        "core/evidence-policy.md",
        (
            ("autonomous current-information research",),
            ("search autonomously",),
            ("current, volatile, disputed, or uncertain",),
            ("primary sources",),
            ("date or version context",),
            ("exclude private learner data",),
            ("learner-profile content",),
            ("session records",),
            ("identifying context",),
            ("no-web fallback",),
            ("continues with stable material",),
        ),
        "current-information research is not autonomous, source-prioritized, and privacy-safe",
        "search current claims autonomously, prefer primary sources, exclude private data, and preserve the no-web fallback",
    ),
)

REQUIRED_DIAGNOSTIC_CODES = tuple(sorted(_contract.code for _contract in _CONTRACTS))

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


def _has_forbidden_marker(text: str, marker: str) -> bool:
    normalized_marker = _normalize(marker)
    negating_prefixes = (
        "do not",
        "don't",
        "never",
        "must not",
        "should not",
        "no",
    )
    negating_suffixes = (
        " is not required",
        " is not needed",
        " is unnecessary",
    )
    search_from = 0
    while (index := text.find(normalized_marker, search_from)) != -1:
        prefix = text[:index]
        suffix = text[index + len(normalized_marker) :]
        has_negating_prefix = any(
            prefix.endswith(f"{negator} ")
            and (
                len(prefix) == len(negator) + 1
                or not prefix[-len(negator) - 2].isalnum()
            )
            for negator in negating_prefixes
        )
        has_negating_suffix = any(
            suffix.startswith(negator)
            and (
                len(suffix) == len(negator)
                or not suffix[len(negator)].isalnum()
            )
            for negator in negating_suffixes
        )
        if not has_negating_prefix and not has_negating_suffix:
            return True
        search_from = index + len(normalized_marker)
    return False


def check_conformance(bundle: str) -> list[Diagnostic]:
    """Return every behavioral contract failure in deterministic order."""

    sections = _source_sections(bundle)
    diagnostics = []
    for contract in _CONTRACTS:
        section = sections.get(contract.path, "")
        has_forbidden_marker = any(
            _has_forbidden_marker(section, marker)
            for marker in contract.forbidden_markers
        )
        if not _has_groups(section, contract.marker_groups) or has_forbidden_marker:
            diagnostics.append(
                Diagnostic(
                    contract.code,
                    contract.path,
                    contract.message,
                    contract.remediation,
                )
            )

    return sorted(diagnostics, key=lambda item: (item.code, item.path))
