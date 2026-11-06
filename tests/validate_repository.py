from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from socratic_learn.build import build_distribution
from socratic_learn.errors import LearningTutorError
from socratic_learn.manifest import validate_manifest

REQUIRED_PATHS = (
    "README.md",
    "LICENSE",
    "AGENTS.md",
    ".gitattributes",
    ".gitignore",
    "core/pedagogy.md",
    "core/session-protocol.md",
    "core/assessment.md",
    "core/evidence-policy.md",
    "curricula/mathematics/map.md",
    "curricula/ai/map.md",
    "templates/learner-profile.md",
    "templates/learning-goal.md",
    "templates/session-log.md",
    "templates/progress.md",
    ".cursor/skills/socratic-learn/SKILL.md",
    "adapters/cursor/README.md",
    "adapters/claude-code/CLAUDE.md",
    "adapters/claude-code/README.md",
    "adapters/pi/skills/socratic-learn/SKILL.md",
    "adapters/pi/skills/socratic-learn/SKILL.project.md.template",
    "adapters/pi/README.md",
    "workspace.example/learner-profile.md",
    "workspace.example/learning-goal.md",
    "workspace.example/progress.md",
    "workspace.example/sessions/2026-01-15-example.md",
    "workspace/.gitkeep",
    "learning_tutor/__init__.py",
    "learning_tutor/__main__.py",
    "socratic_learn/__init__.py",
    "socratic_learn/__main__.py",
    "socratic_learn/build.py",
    "socratic_learn/conformance.py",
    "socratic_learn/doctor.py",
    "socratic_learn/errors.py",
    "socratic_learn/export.py",
    "socratic_learn/install.py",
    "socratic_learn/manifest.py",
    "socratic_learn/templates/generic-loader.md",
    "socratic_learn/templates/cursor-skill.md",
    "socratic_learn/templates/claude-loader.md",
    "socratic_learn/templates/pi-skill.md",
    "dist/socratic-learn.prompt.md",
    "dist/manifest.json",
    "docs/universal-installation.md",
    "docs/manifest-reference.md",
    "docs/adding-an-adapter.md",
    "docs/superpowers/specs/2026-11-05-universal-distribution-design.md",
    "docs/superpowers/plans/2026-11-05-universal-distribution.md",
    "docs/superpowers/specs/2026-11-05-socratic-learn-rename-design.md",
    "docs/superpowers/plans/2026-11-05-socratic-learn-rename.md",
    ".github/workflows/native-python.yml",
)
SKILL_PATHS = (
    ".cursor/skills/socratic-learn/SKILL.md",
    "adapters/pi/skills/socratic-learn/SKILL.md",
)
ADAPTER_ROOTS = (".cursor", "adapters")
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
CANONICAL_RE = re.compile(
    r"<!-- canonical:start -->(.*?)<!-- canonical:end -->",
    re.DOTALL,
)
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FENCE_RE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})")
UNIVERSAL_VALIDATION_INPUTS = (
    "socratic_learn/build.py",
    "dist/socratic-learn.prompt.md",
    "dist/manifest.json",
    "core/pedagogy.md",
    "core/session-protocol.md",
    "core/assessment.md",
    "core/evidence-policy.md",
    "curricula/mathematics/map.md",
    "curricula/ai/map.md",
)
POSIX_THREAT_MODEL_PATHS = (
    "README.md",
    "docs/universal-installation.md",
    "docs/superpowers/specs/2026-11-05-universal-distribution-design.md",
    "docs/superpowers/plans/2026-11-05-universal-distribution.md",
)
POSIX_THREAT_MODEL_TERMS = (
    "ordinary collisions",
    "accidental concurrent changes",
    "cooperating socratic learn processes",
    "same os principal",
    "leaf-entry toctou",
)
IMPOSSIBLE_SAFETY_CLAIM = "no external data was deleted"


def markdown_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*.md")
        if path.is_file()
        and ".git" not in path.relative_to(root).parts
        and "workspace" not in path.relative_to(root).parts
    ]


def without_fenced_code(text: str) -> str:
    visible: list[str] = []
    fence_character = ""
    fence_length = 0
    for line in text.splitlines(keepends=True):
        match = FENCE_RE.match(line)
        if not fence_character:
            if match:
                fence = match.group(1)
                fence_character = fence[0]
                fence_length = len(fence)
            else:
                visible.append(line)
            continue
        if re.fullmatch(
            rf"[ ]{{0,3}}{re.escape(fence_character)}{{{fence_length},}}[ \t]*(?:\r?\n)?",
            line,
        ):
            fence_character = ""
            fence_length = 0
    return "".join(visible)


def markdown_link_target(raw_target: str) -> str:
    raw_target = raw_target.strip()
    if raw_target.startswith("<"):
        end = raw_target.find(">")
        return raw_target[1:end] if end != -1 else raw_target
    return raw_target.split(maxsplit=1)[0] if raw_target else ""


def parse_frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def normalize(text: str) -> str:
    return " ".join(text.split())


def tracked_files(root: Path) -> tuple[set[str], str | None]:
    if not (root / ".git").exists():
        return set(), None
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return set(), "git ls-files unavailable: git executable not found"
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "").strip()
        message = "git ls-files failed"
        if detail:
            message += f": {detail}"
        return set(), message
    return (
        {line.replace("\\", "/") for line in result.stdout.splitlines()},
        None,
    )


def validate_distribution(root: Path) -> list[str]:
    if not all((root / relative).is_file() for relative in UNIVERSAL_VALIDATION_INPUTS):
        return []

    errors: list[str] = []
    bundle_path = root / "dist/socratic-learn.prompt.md"
    manifest_path = root / "dist/manifest.json"
    try:
        bundle = bundle_path.read_bytes()
        manifest_bytes = manifest_path.read_bytes()
    except OSError as error:
        return [f"Generated distribution could not be read: {error}"]

    if not bundle.startswith(b"# Socratic Learn\n"):
        errors.append(
            "Generated bundle does not have the expected header: "
            "# Socratic Learn"
        )

    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
        validate_manifest(manifest)
    except (UnicodeDecodeError, json.JSONDecodeError, LearningTutorError) as error:
        errors.append(f"Generated manifest is invalid: {error}")

    try:
        expected = build_distribution(root)
    except LearningTutorError as error:
        errors.append(f"In-memory distribution build failed: {error}")
        return errors

    if bundle != expected.bundle or manifest_bytes != expected.manifest:
        errors.append(
            "Found stale generated artifacts in dist/; run: "
            "python -m learning_tutor build"
        )
    return errors


def validate(root: Path) -> list[str]:
    errors: list[str] = []

    for relative in REQUIRED_PATHS:
        path = root / relative
        if path.is_file():
            continue
        if not path.exists():
            errors.append(f"Missing required path: {relative}")
        elif path.is_dir():
            errors.append(
                f"Required path is not a file: {relative} (found directory)"
            )
        else:
            errors.append(
                f"Required path is not a file: {relative} (found non-file)"
            )

    for relative in POSIX_THREAT_MODEL_PATHS:
        path = root / relative
        if not path.is_file():
            continue
        text = normalize(path.read_text(encoding="utf-8")).lower()
        missing = [
            term for term in POSIX_THREAT_MODEL_TERMS if term not in text
        ]
        if missing:
            errors.append(
                f"Missing POSIX same-principal threat model in {relative}: "
                + ", ".join(missing)
            )

    claim_paths = [
        root / "README.md",
        *(root / "docs").rglob("*.md"),
        *(root / "socratic_learn").rglob("*.py"),
    ]
    for path in claim_paths:
        if (
            path.is_file()
            and IMPOSSIBLE_SAFETY_CLAIM
            in path.read_text(encoding="utf-8").lower()
        ):
            relative = path.relative_to(root)
            errors.append(
                f"Impossible absolute filesystem safety claim in {relative}: "
                f"{IMPOSSIBLE_SAFETY_CLAIM}"
            )

    for path in markdown_files(root):
        text = path.read_text(encoding="utf-8")
        visible_text = without_fenced_code(text)
        for raw_target in LINK_RE.findall(visible_text):
            target = markdown_link_target(raw_target)
            target = target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (path.parent / target).resolve().exists():
                errors.append(
                    f"Broken Markdown link in {path.relative_to(root)}: {target}"
                )
        if any(
            line.strip() == "PRIVATE_LEARNER_DATA"
            for line in visible_text.splitlines()
        ):
            errors.append(
                f"Found private learner marker outside workspace: {path.relative_to(root)}"
            )

    for relative in SKILL_PATHS:
        path = root / relative
        if not path.is_file():
            continue
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8"))
        if (
            frontmatter is None
            or not SKILL_NAME_RE.fullmatch(frontmatter.get("name", ""))
            or frontmatter.get("name") != path.parent.name
            or frontmatter.get("name") != "socratic-learn"
            or not frontmatter.get("description")
        ):
            errors.append(f"Invalid skill frontmatter: {relative}")

    canonical_blocks: list[str] = []
    core = root / "core"
    if core.exists():
        for path in core.glob("*.md"):
            if not path.is_file():
                continue
            canonical_blocks.extend(
                normalize(block)
                for block in CANONICAL_RE.findall(
                    path.read_text(encoding="utf-8")
                )
                if len(normalize(block)) >= 40
            )

    for adapter_root in ADAPTER_ROOTS:
        base = root / adapter_root
        if not base.exists():
            continue
        for path in base.rglob("*.md"):
            if not path.is_file():
                continue
            adapter_text = normalize(path.read_text(encoding="utf-8"))
            for block in canonical_blocks:
                if block in adapter_text:
                    errors.append(
                        f"{path.relative_to(root)} duplicates canonical core text"
                    )
                    break

    gitignore = root / ".gitignore"
    if gitignore.is_file():
        rules = gitignore.read_text(encoding="utf-8").splitlines()
        if "workspace/*" not in rules or "!workspace/.gitkeep" not in rules:
            errors.append(".gitignore must ignore workspace except .gitkeep")

    gitattributes = root / ".gitattributes"
    if gitattributes.is_file():
        rules = gitattributes.read_text(encoding="utf-8").splitlines()
        if "dist/* text eol=lf" not in rules:
            errors.append(".gitattributes must enforce LF for dist/*")

    tracked, git_error = tracked_files(root)
    if git_error:
        errors.append(git_error)
    tracked_private = sorted(
        path
        for path in tracked
        if path.startswith("workspace/") and path != "workspace/.gitkeep"
    )
    if tracked_private:
        errors.append("Tracked private learner files: " + ", ".join(tracked_private))

    errors.extend(validate_distribution(root))
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = validate(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Repository validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
