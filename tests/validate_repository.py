from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from learning_tutor.build import build_distribution
from learning_tutor.errors import LearningTutorError
from learning_tutor.manifest import validate_manifest

REQUIRED_PATHS = (
    "README.md",
    "AGENTS.md",
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
    ".cursor/skills/learning-tutor/SKILL.md",
    "adapters/cursor/README.md",
    "adapters/claude-code/CLAUDE.md",
    "adapters/claude-code/README.md",
    "adapters/pi/skills/learning-tutor/SKILL.md",
    "adapters/pi/skills/learning-tutor/SKILL.project.md.template",
    "adapters/pi/README.md",
    "workspace.example/learner-profile.md",
    "workspace.example/learning-goal.md",
    "workspace.example/progress.md",
    "workspace.example/sessions/2026-01-15-example.md",
    "workspace/.gitkeep",
    "learning_tutor/__init__.py",
    "learning_tutor/__main__.py",
    "learning_tutor/build.py",
    "learning_tutor/conformance.py",
    "learning_tutor/doctor.py",
    "learning_tutor/errors.py",
    "learning_tutor/export.py",
    "learning_tutor/install.py",
    "learning_tutor/manifest.py",
    "learning_tutor/templates/generic-loader.md",
    "learning_tutor/templates/cursor-skill.md",
    "learning_tutor/templates/claude-loader.md",
    "learning_tutor/templates/pi-skill.md",
    "dist/learning-tutor.prompt.md",
    "dist/manifest.json",
    "docs/universal-installation.md",
    "docs/manifest-reference.md",
    "docs/adding-an-adapter.md",
)
SKILL_PATHS = (
    ".cursor/skills/learning-tutor/SKILL.md",
    "adapters/pi/skills/learning-tutor/SKILL.md",
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
    "learning_tutor/build.py",
    "dist/learning-tutor.prompt.md",
    "dist/manifest.json",
    "core/pedagogy.md",
    "core/session-protocol.md",
    "core/assessment.md",
    "core/evidence-policy.md",
    "curricula/mathematics/map.md",
    "curricula/ai/map.md",
)


def markdown_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*.md")
        if ".git" not in path.relative_to(root).parts
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
    bundle_path = root / "dist/learning-tutor.prompt.md"
    manifest_path = root / "dist/manifest.json"
    try:
        bundle = bundle_path.read_bytes()
        manifest_bytes = manifest_path.read_bytes()
    except OSError as error:
        return [f"Generated distribution could not be read: {error}"]

    if not bundle.startswith(b"# Universal Learning Tutor\n"):
        errors.append(
            "Generated bundle does not have the expected header: "
            "# Universal Learning Tutor"
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
        if not (root / relative).exists():
            errors.append(f"Missing required path: {relative}")

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
        if not path.exists():
            continue
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8"))
        if (
            frontmatter is None
            or not SKILL_NAME_RE.fullmatch(frontmatter.get("name", ""))
            or frontmatter.get("name") != path.parent.name
            or frontmatter.get("name") != "learning-tutor"
            or not frontmatter.get("description")
        ):
            errors.append(f"Invalid skill frontmatter: {relative}")

    canonical_blocks: list[str] = []
    core = root / "core"
    if core.exists():
        for path in core.glob("*.md"):
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
            adapter_text = normalize(path.read_text(encoding="utf-8"))
            for block in canonical_blocks:
                if block in adapter_text:
                    errors.append(
                        f"{path.relative_to(root)} duplicates canonical core text"
                    )
                    break

    gitignore = root / ".gitignore"
    if gitignore.exists():
        rules = gitignore.read_text(encoding="utf-8").splitlines()
        if "workspace/*" not in rules or "!workspace/.gitkeep" not in rules:
            errors.append(".gitignore must ignore workspace except .gitkeep")

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
