"""Deterministic manifest serialization and validation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import PurePosixPath, PureWindowsPath

from . import MANIFEST_SCHEMA_VERSION, PRODUCT_ID, PROTOCOL_VERSION, TARGETS
from .conformance import CONFORMANCE_CONTRACT_VERSION, REQUIRED_DIAGNOSTIC_CODES
from .errors import IntegrityError


SESSION_HEADINGS = (
    "## Outcome",
    "## Diagnostic evidence",
    "## Approved dependency path",
    "## Concepts established",
    "## Application evidence",
    "## Remaining gaps",
    "## Next step",
    "## Sources",
)

CAPABILITY_FALLBACKS = {
    "cross_session_memory": "Ask for a prior summary and state what is unknown.",
    "diagram_rendering": "Use Mermaid if available or a textual edge list.",
    "filesystem": "Return the complete session record as Markdown.",
    "structured_quiz": "Ask one question at a time in conversation.",
    "subagents": "Research and teach sequentially.",
    "web": "Mark volatile claims unverified and prefer stable content.",
}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOP_LEVEL_KEYS = {
    "bundle",
    "capability_fallbacks",
    "conformance",
    "language",
    "product",
    "protocol_version",
    "schema_version",
    "session_headings",
    "sources",
    "targets",
}
_SOURCE_KEYS = {"path", "sha256"}
_BUNDLE_KEYS = {"path", "sha256"}
_CONFORMANCE_KEYS = {"required_diagnostic_codes", "version"}
BUNDLE_NAME = "socratic-learn.prompt.md"
_REMEDIATION = "regenerate the manifest with 'socratic-learn build'"


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase SHA-256 digest for *data*."""

    return hashlib.sha256(data).hexdigest()


def serialize_json(value: object) -> bytes:
    """Serialize JSON with stable ordering, formatting, and termination."""

    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _is_relative_portable_path(value: object) -> bool:
    if (
        type(value) is not str
        or not value
        or "\\" in value
        or _has_control_character(value)
    ):
        return False
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    return (
        not posix.is_absolute()
        and not windows.is_absolute()
        and windows.drive == ""
        and ".." not in posix.parts
        and value == posix.as_posix()
    )


def _has_control_character(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


def _invalid(field: str, message: str) -> IntegrityError:
    return IntegrityError(
        f"manifest {field} {message}",
        path=f"manifest.{field}",
        remediation=_REMEDIATION,
    )


def _require_exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    field: str,
) -> None:
    actual = set(value)
    unknown = sorted(actual - expected)
    if unknown:
        unknown_field = f"{field}.{unknown[0]}" if field else unknown[0]
        raise _invalid(unknown_field, "is an unknown property")
    missing = sorted(expected - actual)
    if missing:
        missing_field = f"{field}.{missing[0]}" if field else missing[0]
        raise _invalid(missing_field, "is required")


def _require_hash(value: object, field: str) -> None:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _invalid(field, "must be a lowercase SHA-256 hash")


def validate_manifest(manifest: Mapping[str, object]) -> None:
    """Reject manifests that drift from the distribution contract."""

    if not isinstance(manifest, Mapping):
        raise _invalid("$", "must be a JSON object")
    _require_exact_keys(manifest, _TOP_LEVEL_KEYS, "")

    schema_version = manifest["schema_version"]
    if type(schema_version) is not int or schema_version != MANIFEST_SCHEMA_VERSION:
        raise _invalid(
            "schema_version",
            f"must be integer {MANIFEST_SCHEMA_VERSION}",
        )
    product = manifest["product"]
    if type(product) is not str or product != PRODUCT_ID:
        raise _invalid("product", f"must be '{PRODUCT_ID}'")
    protocol_version = manifest["protocol_version"]
    if type(protocol_version) is not str or protocol_version != PROTOCOL_VERSION:
        raise _invalid("protocol_version", f"must be '{PROTOCOL_VERSION}'")
    language = manifest["language"]
    if type(language) is not str or language != "en":
        raise _invalid("language", "must be 'en'")
    targets = manifest["targets"]
    if type(targets) is not list or any(type(target) is not str for target in targets):
        raise _invalid("targets", "must be an array of strings")
    if targets != list(TARGETS):
        raise _invalid("targets", "must match the exact target sequence")

    sources = manifest["sources"]
    if type(sources) is not list or not sources:
        raise _invalid("sources", "must be a non-empty array")
    seen_paths: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, Mapping):
            raise _invalid(f"sources[{index}]", "must be a JSON object")
        _require_exact_keys(source, _SOURCE_KEYS, f"sources[{index}]")
        path = source["path"]
        if not _is_relative_portable_path(path):
            raise _invalid(
                f"sources[{index}].path",
                "must be a control-free relative POSIX path",
            )
        assert isinstance(path, str)
        if path in seen_paths:
            raise _invalid(f"sources[{index}].path", f"is a duplicate source path: {path}")
        seen_paths.add(path)
        _require_hash(source["sha256"], f"sources[{index}].sha256")

    bundle = manifest["bundle"]
    if not isinstance(bundle, Mapping):
        raise _invalid("bundle", "must be a JSON object")
    _require_exact_keys(bundle, _BUNDLE_KEYS, "bundle")
    bundle_path = bundle["path"]
    if type(bundle_path) is not str or bundle_path != BUNDLE_NAME:
        raise _invalid("bundle.path", f"must be {BUNDLE_NAME}")
    _require_hash(bundle["sha256"], "bundle.sha256")

    fallbacks = manifest["capability_fallbacks"]
    if not isinstance(fallbacks, Mapping):
        raise _invalid("capability_fallbacks", "must be a JSON object")
    _require_exact_keys(
        fallbacks,
        set(CAPABILITY_FALLBACKS),
        "capability_fallbacks",
    )
    for capability, fallback in fallbacks.items():
        if (
            type(fallback) is not str
            or not fallback.strip()
            or _has_control_character(fallback)
        ):
            raise _invalid(
                f"capability_fallbacks.{capability}",
                "must be a non-empty control-free string",
            )

    conformance = manifest["conformance"]
    if not isinstance(conformance, Mapping):
        raise _invalid("conformance", "must be a JSON object")
    _require_exact_keys(conformance, _CONFORMANCE_KEYS, "conformance")
    version = conformance["version"]
    if type(version) is not int or version != CONFORMANCE_CONTRACT_VERSION:
        raise _invalid(
            "conformance.version",
            f"must be integer {CONFORMANCE_CONTRACT_VERSION}",
        )
    required_codes = conformance["required_diagnostic_codes"]
    if (
        type(required_codes) is not list
        or any(type(code) is not str for code in required_codes)
        or required_codes != list(REQUIRED_DIAGNOSTIC_CODES)
    ):
        raise _invalid(
            "conformance.required_diagnostic_codes",
            "must match the exact behavioral contract code sequence",
        )

    headings = manifest["session_headings"]
    if type(headings) is not list or any(type(item) is not str for item in headings):
        raise _invalid("session_headings", "must be an array of strings")
    if headings != list(SESSION_HEADINGS):
        raise _invalid("session_headings", "must match the exact heading sequence")
