"""Filesystem isolation and protocol identity for private semantic evaluation runs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from evaluation.sanitize import write_private
from evaluation.schema import canonical_json
from socratic_learn import PROTOCOL_VERSION
from socratic_learn.build import build_distribution
from socratic_learn.manifest import BUNDLE_NAME
from socratic_learn.workspace import prepare_personal_workspace


RULE_MARKERS = ("AGENTS.md", "GEMINI.md", "CLAUDE.md", ".agents", ".agent")
USER_HOME_RULE_PATHS = (
    "AGENTS.md",
    "GEMINI.md",
    "CLAUDE.md",
    ".agents",
    ".agent",
    ".gemini/GEMINI.md",
)

RuleBoundary = Literal["user_home", "filesystem_root"]
_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_RUNTIME_CONTEXT_KEYS = {
    "runtime_root",
    "runtime_outside_repository",
    "local_rule_check_passed",
    "rule_boundary",
    "user_home_rule_paths",
    "above_home_markers",
}


class LocalRuleContamination(ValueError):
    """Raised when a runtime cwd would inherit a local rule marker."""


@dataclass(frozen=True)
class AboveHomeMarker:
    levels_above_home: int
    marker: str


@dataclass(frozen=True)
class RuleDisclosure:
    boundary: RuleBoundary
    user_home_rule_paths: tuple[str, ...]
    above_home_markers: tuple[AboveHomeMarker, ...]


@dataclass(frozen=True)
class RunLayout:
    run_dir: Path
    raw: Path
    evaluator: Path
    runtime_root: Path
    owns_runtime_root: bool
    home: Path
    cwd: Path
    records: Path
    protocol: Path
    user_home: Path
    rule_disclosure: RuleDisclosure


@dataclass(frozen=True)
class RuntimeContext:
    runtime_root: Path
    runtime_outside_repository: bool
    local_rule_check_passed: bool
    rule_disclosure: RuleDisclosure


@dataclass(frozen=True)
class ProtocolIdentity:
    repository_commit: str
    protocol_version: str
    bundle_sha256: str


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.normpath(os.fspath(path)))


def _same_path(left: Path, right: Path) -> bool:
    return _path_key(left) == _path_key(right)


def _contains(parent: Path, candidate: Path) -> bool:
    parent_key = _path_key(parent)
    candidate_key = _path_key(candidate)
    try:
        return os.path.commonpath((parent_key, candidate_key)) == parent_key
    except ValueError:
        return False


def _strictly_contains(parent: Path, candidate: Path) -> bool:
    return _contains(parent, candidate) and not _same_path(parent, candidate)


def _resolved(path: Path, *, strict: bool) -> Path:
    try:
        return path.resolve(strict=strict)
    except OSError as error:
        raise ValueError("path cannot be resolved safely") from error


def _is_link_or_reparse(path: Path) -> bool:
    """Classify symlinks, junctions, and other Windows reparse-point entries."""
    try:
        status = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise ValueError("filesystem entry cannot be inspected safely") from error
    attributes = getattr(status, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(status.st_mode) or bool(attributes & reparse_flag)


def _assert_no_link_components(path: Path, *, stop: Path | None = None) -> None:
    """Reject every existing link/reparse component from path up to stop/root."""
    current = _absolute(path)
    stop_path = _absolute(stop) if stop is not None else None
    while True:
        if os.path.lexists(current) and _is_link_or_reparse(current):
            raise ValueError("path contains a link or reparse-point component")
        if stop_path is not None and _same_path(current, stop_path):
            return
        parent = current.parent
        if parent == current:
            if stop_path is not None:
                raise ValueError("path is outside the required boundary")
            return
        current = parent


def _require_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase hyphenated identifier")


def _require_directory(path: Path, label: str) -> Path:
    absolute = _absolute(path)
    _assert_no_link_components(absolute)
    resolved = _resolved(absolute, strict=True)
    if not resolved.is_dir():
        raise ValueError(f"{label} must be a regular directory")
    return resolved


def _runtime_is_separate(runtime_root: Path, repository: Path, raw_root: Path) -> bool:
    return (
        not _contains(repository, runtime_root)
        and not _contains(raw_root, runtime_root)
        and not _contains(runtime_root, repository)
        and not _contains(runtime_root, raw_root)
    )


def assert_no_local_rule_ancestors(cwd: Path, user_home: Path) -> RuleBoundary:
    """Check cwd ancestry using existence checks only, excluding the home boundary."""
    current = _resolved(_absolute(cwd), strict=True)
    home = _resolved(_absolute(user_home), strict=True)
    home_boundary = _contains(home, current)
    levels = 0

    while True:
        if home_boundary and _same_path(current, home):
            return "user_home"
        for marker in RULE_MARKERS:
            if os.path.lexists(current / marker):
                raise LocalRuleContamination(
                    f"local rule marker {marker!r} found {levels} levels above cwd"
                )
        parent = current.parent
        if parent == current:
            return "filesystem_root"
        current = parent
        levels += 1


def disclose_rule_markers(
    user_home: Path,
    boundary: RuleBoundary,
) -> RuleDisclosure:
    """Disclose inherited rules by relative name/level without reading their content."""
    if boundary not in ("user_home", "filesystem_root"):
        raise ValueError("unsupported rule boundary")
    home = _resolved(_absolute(user_home), strict=True)
    home_rules = tuple(
        relative
        for relative in USER_HOME_RULE_PATHS
        if os.path.lexists(home.joinpath(*relative.split("/")))
    )
    above: list[AboveHomeMarker] = []
    if home.parent == home:
        return RuleDisclosure(boundary, home_rules, ())
    current = home.parent
    level = 1
    while True:
        for marker in RULE_MARKERS:
            if os.path.lexists(current / marker):
                above.append(AboveHomeMarker(level, marker))
        parent = current.parent
        if parent == current:
            break
        current = parent
        level += 1
    return RuleDisclosure(boundary, home_rules, tuple(above))


def _runtime_context_document(
    runtime_root: Path,
    disclosure: RuleDisclosure,
) -> dict[str, object]:
    return {
        "runtime_root": str(runtime_root),
        "runtime_outside_repository": True,
        "local_rule_check_passed": True,
        "rule_boundary": disclosure.boundary,
        "user_home_rule_paths": list(disclosure.user_home_rule_paths),
        "above_home_markers": [
            {
                "levels_above_home": item.levels_above_home,
                "marker": item.marker,
            }
            for item in disclosure.above_home_markers
        ],
    }


def _tree_contains_links(root: Path) -> bool:
    if _is_link_or_reparse(root):
        return True
    for directory, names, files in os.walk(root, topdown=True, followlinks=False):
        base = Path(directory)
        for name in (*names, *files):
            if _is_link_or_reparse(base / name):
                return True
    return False


def _remove_created_runtime(runtime_root: Path) -> None:
    if not os.path.lexists(runtime_root):
        return
    if _tree_contains_links(runtime_root):
        raise ValueError("runtime root contains a link or reparse point")
    shutil.rmtree(runtime_root)


def create_run_layout(
    repository: Path,
    suite_id: str,
    scenario_id: str,
    *,
    raw_root: Path | None = None,
    runtime_base: Path | None = None,
    user_home: Path | None = None,
) -> RunLayout:
    """Create private repository evidence and one external per-run workspace."""
    _require_identifier(suite_id, "suite_id")
    _require_identifier(scenario_id, "scenario_id")
    repository_root = _require_directory(repository, "repository")
    home_boundary = _require_directory(
        Path.home() if user_home is None else user_home,
        "user_home",
    )

    raw_candidate = _absolute(
        repository_root / ".semantic-runs" if raw_root is None else raw_root
    )
    _assert_no_link_components(raw_candidate, stop=repository_root)
    resolved_raw = _resolved(raw_candidate, strict=False)
    if not _strictly_contains(repository_root, resolved_raw):
        raise ValueError("raw_root must be inside the repository")
    run_dir = _resolved(resolved_raw / suite_id / scenario_id, strict=False)
    if not _strictly_contains(resolved_raw, run_dir):
        raise ValueError("run directory must be inside raw_root")
    if os.path.lexists(run_dir):
        raise ValueError("run directory already exists")

    owns_runtime_root = runtime_base is None
    runtime_root: Path | None = None
    expected_runtime_root: Path | None = None
    if runtime_base is not None:
        shared_base = _require_directory(runtime_base, "runtime_base")
        candidate = _absolute(shared_base / suite_id / scenario_id)
        _assert_no_link_components(candidate)
        candidate = _resolved(candidate, strict=False)
        if not _strictly_contains(shared_base, candidate):
            raise ValueError("runtime root must be inside runtime_base")
        if not _runtime_is_separate(candidate, repository_root, resolved_raw):
            raise ValueError("runtime root must be outside repository evidence")
        if _contains(candidate, home_boundary):
            raise ValueError("runtime root must not own the user home boundary")
        if os.path.lexists(candidate):
            raise ValueError("runtime root already exists")
        expected_runtime_root = candidate

    run_created = False
    try:
        if runtime_base is None:
            runtime_root = Path(
                tempfile.mkdtemp(prefix="socratic-semantic-")
            ).resolve(strict=True)
        else:
            runtime_root = candidate
            runtime_root.mkdir(parents=True)
            runtime_root = runtime_root.resolve(strict=True)

        _assert_no_link_components(runtime_root)
        if (
            expected_runtime_root is not None
            and (
                not _same_path(runtime_root, expected_runtime_root)
                or not _strictly_contains(shared_base, runtime_root)
            )
        ):
            raise ValueError("runtime root changed during creation")
        if not _runtime_is_separate(runtime_root, repository_root, resolved_raw):
            raise ValueError("runtime root must be outside repository evidence")
        if _contains(runtime_root, home_boundary):
            raise ValueError("runtime root must not own the user home boundary")

        workspace = prepare_personal_workspace(runtime_root / "home")
        boundary = assert_no_local_rule_ancestors(workspace.root, home_boundary)
        disclosure = disclose_rule_markers(home_boundary, boundary)

        run_dir.mkdir(parents=True)
        run_created = True
        _assert_no_link_components(run_dir, stop=repository_root)
        created_run_dir = _resolved(run_dir, strict=True)
        if (
            not _same_path(created_run_dir, run_dir)
            or not _strictly_contains(resolved_raw, created_run_dir)
        ):
            raise ValueError("run directory changed during creation")
        raw = run_dir / "raw"
        evaluator = run_dir / "evaluator"
        raw.mkdir()
        evaluator.mkdir()
        write_private(
            run_dir / "runtime-context.json",
            canonical_json(_runtime_context_document(runtime_root, disclosure)),
            private_root=run_dir,
        )
        return RunLayout(
            run_dir=run_dir,
            raw=raw,
            evaluator=evaluator,
            runtime_root=runtime_root,
            owns_runtime_root=owns_runtime_root,
            home=runtime_root / "home",
            cwd=workspace.root,
            records=workspace.records,
            protocol=workspace.protocol,
            user_home=home_boundary,
            rule_disclosure=disclosure,
        )
    except BaseException:
        if run_created and os.path.lexists(run_dir) and not _tree_contains_links(run_dir):
            shutil.rmtree(run_dir)
        if runtime_root is not None:
            _remove_created_runtime(runtime_root)
        raise


def _string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")
    return tuple(value)


def load_runtime_context(run_dir: Path) -> RuntimeContext:
    """Load and strictly validate one private runtime-context document."""
    path = Path(run_dir) / "runtime-context.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("runtime context is unavailable or invalid") from error
    if not isinstance(document, dict) or set(document) != _RUNTIME_CONTEXT_KEYS:
        raise ValueError("runtime context has an invalid shape")
    if document["runtime_outside_repository"] is not True:
        raise ValueError("runtime context does not confirm external isolation")
    if document["local_rule_check_passed"] is not True:
        raise ValueError("runtime context does not confirm the local rule check")
    boundary = document["rule_boundary"]
    if boundary not in ("user_home", "filesystem_root"):
        raise ValueError("runtime context has an invalid rule boundary")
    root_value = document["runtime_root"]
    if not isinstance(root_value, str) or not Path(root_value).is_absolute():
        raise ValueError("runtime context has an invalid runtime root")
    raw_markers = document["above_home_markers"]
    if not isinstance(raw_markers, list):
        raise ValueError("runtime context above-home markers must be a list")
    markers: list[AboveHomeMarker] = []
    for item in raw_markers:
        if not isinstance(item, dict) or set(item) != {"levels_above_home", "marker"}:
            raise ValueError("runtime context has an invalid above-home marker")
        level = item["levels_above_home"]
        marker = item["marker"]
        if (
            isinstance(level, bool)
            or not isinstance(level, int)
            or level < 1
            or marker not in RULE_MARKERS
        ):
            raise ValueError("runtime context has an invalid above-home marker")
        markers.append(AboveHomeMarker(level, marker))
    disclosure = RuleDisclosure(
        boundary=boundary,
        user_home_rule_paths=_string_list(
            document["user_home_rule_paths"],
            "runtime context user-home rules",
        ),
        above_home_markers=tuple(markers),
    )
    if any(path not in USER_HOME_RULE_PATHS for path in disclosure.user_home_rule_paths):
        raise ValueError("runtime context has an invalid user-home rule path")
    return RuntimeContext(
        runtime_root=Path(root_value),
        runtime_outside_repository=True,
        local_rule_check_passed=True,
        rule_disclosure=disclosure,
    )


def _relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _read_regular_file(path: Path) -> bytes:
    before = os.lstat(path)
    if (
        not stat.S_ISREG(before.st_mode)
        or _is_link_or_reparse(path)
    ):
        raise ValueError("learner record is not a regular unlinked file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags | nofollow)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError("learner record changed while it was opened")
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("learner record changed while it was opened")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def snapshot_learner_records(layout: RunLayout) -> Path:
    """Copy regular learner records while explicitly pruning every linked directory."""
    source = layout.records
    if _is_link_or_reparse(source) or not source.is_dir():
        raise ValueError("learner records root must be a regular directory")
    destination = layout.run_dir / "learner-records"
    skipped_path = layout.run_dir / "skipped-links.json"
    if os.path.lexists(destination) or os.path.lexists(skipped_path):
        raise ValueError("learner records snapshot already exists")
    destination.mkdir(mode=0o700)
    skipped: list[str] = []
    try:
        for directory, names, files in os.walk(source, topdown=True, followlinks=False):
            current = Path(directory)
            relative_directory = current.relative_to(source)
            if relative_directory != Path("."):
                (destination / relative_directory).mkdir(mode=0o700)

            retained: list[str] = []
            for name in sorted(names):
                entry = current / name
                relative = _relative_posix(entry, source)
                if _is_link_or_reparse(entry):
                    skipped.append(relative)
                    continue
                status = os.lstat(entry)
                if stat.S_ISDIR(status.st_mode):
                    retained.append(name)
            names[:] = retained

            for name in sorted(files):
                entry = current / name
                relative = _relative_posix(entry, source)
                if _is_link_or_reparse(entry):
                    skipped.append(relative)
                    continue
                status = os.lstat(entry)
                if not stat.S_ISREG(status.st_mode):
                    continue
                write_private(
                    destination / relative,
                    _read_regular_file(entry),
                    private_root=destination,
                )
        write_private(
            skipped_path,
            canonical_json(sorted(skipped)),
            private_root=layout.run_dir,
        )
        return destination
    except BaseException:
        if destination.exists():
            shutil.rmtree(destination)
        raise


def _validate_layout_contract(layout: RunLayout) -> None:
    expected = (
        (layout.raw, layout.run_dir / "raw"),
        (layout.evaluator, layout.run_dir / "evaluator"),
        (layout.home, layout.runtime_root / "home"),
        (layout.cwd, layout.runtime_root / "home" / "learning"),
        (
            layout.records,
            layout.runtime_root
            / "home"
            / "learning"
            / ".socratic-learn"
            / "workspace",
        ),
        (
            layout.protocol,
            layout.runtime_root
            / "home"
            / "learning"
            / ".socratic-learn"
            / "socratic-learn.prompt.md",
        ),
    )
    if any(not _same_path(actual, wanted) for actual, wanted in expected):
        raise ValueError("run layout paths are outside the cleanup contract")
    context = load_runtime_context(layout.run_dir)
    if not _same_path(context.runtime_root, layout.runtime_root):
        raise ValueError("runtime root differs from the recorded cleanup contract")


def remove_runtime_root(layout: RunLayout, repository: Path) -> None:
    """Remove only the recorded per-run runtime, never shared/protected roots."""
    repository_root = _require_directory(repository, "repository")
    _validate_layout_contract(layout)
    runtime_root = _absolute(layout.runtime_root)
    if not os.path.lexists(runtime_root):
        return
    if _is_link_or_reparse(runtime_root):
        raise ValueError("runtime root must not be a link or reparse point")
    resolved_runtime = _resolved(runtime_root, strict=True)
    raw_root = _resolved(_absolute(layout.run_dir.parent.parent), strict=True)
    user_home = _resolved(_absolute(layout.user_home), strict=True)
    actual_user_home = _resolved(_absolute(Path.home()), strict=True)

    if (
        _contains(repository_root, resolved_runtime)
        or _contains(raw_root, resolved_runtime)
        or _contains(resolved_runtime, repository_root)
        or _contains(resolved_runtime, raw_root)
        or _contains(resolved_runtime, user_home)
        or _contains(resolved_runtime, actual_user_home)
    ):
        raise ValueError("refusing to remove a protected or overlapping path")
    if _tree_contains_links(resolved_runtime):
        raise ValueError("runtime root contains a link or reparse point")
    shutil.rmtree(resolved_runtime)


def isolated_environment(
    layout: RunLayout,
    parent: Mapping[str, str],
) -> dict[str, str]:
    """Inherit runtime/auth state while selecting only Socratic Learn's private home."""
    environment = dict(parent)
    environment["SOCRATIC_LEARN_HOME"] = str(layout.home)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def capture_protocol_identity(repository: Path) -> ProtocolIdentity:
    """Capture the commit/version/hash identity of the unchanged built protocol."""
    repository_root = _require_directory(repository, "repository")
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=repository_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    commit = completed.stdout.strip().lower()
    if re.fullmatch(r"[0-9a-f]{40,64}", commit) is None:
        raise ValueError("repository commit identity is invalid")

    built = build_distribution(repository_root)
    try:
        checked_bundle = (repository_root / "dist" / BUNDLE_NAME).read_bytes()
        checked_manifest = (repository_root / "dist" / "manifest.json").read_bytes()
    except OSError as error:
        raise ValueError("checked-in distribution is unavailable") from error
    if built.bundle != checked_bundle or built.manifest != checked_manifest:
        raise ValueError("checked-in distribution differs from the current protocol build")
    return ProtocolIdentity(
        repository_commit=commit,
        protocol_version=PROTOCOL_VERSION,
        bundle_sha256=hashlib.sha256(built.bundle).hexdigest(),
    )


def assert_protocol_unchanged(
    expected: ProtocolIdentity,
    repository: Path,
) -> None:
    """Reject any commit, protocol-version, or built-bundle identity drift."""
    actual = capture_protocol_identity(repository)
    if actual != expected:
        raise ValueError("protocol identity changed during the evaluation run")
