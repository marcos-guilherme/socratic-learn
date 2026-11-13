import ast
from pathlib import Path


def test_pixel_scenes_source_never_imports_socratic_learn():
    source_root = Path(__file__).parents[1] / "src" / "pixel_scenes"
    offenders = []
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any(name == "socratic_learn" or name.startswith("socratic_learn.") for name in names):
                offenders.append(path)
    assert offenders == []
