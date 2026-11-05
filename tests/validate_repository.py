from __future__ import annotations

import re
import subprocess
from pathlib import Path

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
    "adapters/pi/skills/learning-tutor/SKILL.md",
    "workspace/.gitkeep",
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
        if "PRIVATE_LEARNER_DATA" in visible_text:
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
