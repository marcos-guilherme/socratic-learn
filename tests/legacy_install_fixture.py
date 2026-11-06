from __future__ import annotations

import hashlib
import json
from pathlib import Path


def create_valid_legacy_install(project: Path, *, target: str) -> None:
    root = project / ".learning-tutor"
    root.mkdir()
    files = {
        ".learning-tutor/manifest.json": b'{"schema_version":1}\n',
        ".learning-tutor/learning-tutor.prompt.md": (
            b"# Universal Learning Tutor\n"
        ),
        ".learning-tutor/loader.md": (
            b"Load .learning-tutor/learning-tutor.prompt.md\n"
        ),
        ".learning-tutor/.gitignore": b"workspace/*\n!workspace/.gitkeep\n",
        ".learning-tutor/workspace/.gitkeep": b"",
    }
    native = {
        "cursor": ".cursor/skills/learning-tutor/SKILL.md",
        "pi": ".pi/skills/learning-tutor/SKILL.md",
    }.get(target)
    if native is not None:
        files[native] = b"---\nname: learning-tutor\n---\n"
    for relative, content in files.items():
        path = project.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    owned = sorted((*files, ".learning-tutor/install.json"))
    receipt = {
        "schema_version": 1,
        "protocol_version": "1.0.0",
        "target": target,
        "owned_paths": owned,
        "hashes": {
            relative: hashlib.sha256(content).hexdigest()
            for relative, content in sorted(files.items())
        },
    }
    (root / "install.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def snapshot_tree(project: Path) -> tuple[tuple[str, str, bytes], ...]:
    entries: list[tuple[str, str, bytes]] = []
    for path in sorted(project.rglob("*")):
        relative = path.relative_to(project).as_posix()
        if path.is_symlink():
            entries.append(
                (relative, "symlink", path.readlink().as_posix().encode())
            )
        elif path.is_file():
            entries.append((relative, "file", path.read_bytes()))
        else:
            entries.append((relative, "directory", b""))
    return tuple(entries)
