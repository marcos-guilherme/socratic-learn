from pathlib import Path
import subprocess
import sys

from PyInstaller.utils.hooks import collect_submodules


root = Path(SPECPATH).resolve()

for pattern in ("*.whl", "*.tar.gz"):
    for generated_package in (root / "dist").glob(pattern):
        generated_package.unlink()

subprocess.run(
    [sys.executable, "-m", "socratic_learn", "build"],
    cwd=root,
    check=True,
)
subprocess.run(
    ["git", "diff", "--exit-code", "--", "dist"],
    cwd=root,
    check=True,
)
distribution_status = subprocess.run(
    ["git", "status", "--porcelain", "--untracked-files=all", "--", "dist"],
    cwd=root,
    check=True,
    capture_output=True,
    text=True,
).stdout
if distribution_status:
    raise SystemExit(
        "generated distribution differs from the checked-in files:\n"
        + distribution_status
    )

datas = [
    (str(root / "dist" / "manifest.json"), "socratic_learn/data"),
    (
        str(root / "dist" / "socratic-learn.prompt.md"),
        "socratic_learn/data",
    ),
]
datas.extend(
    (
        str(root / "templates" / name),
        "socratic_learn/data/templates",
    )
    for name in (
        "learner-profile.md",
        "learning-goal.md",
        "progress.md",
        "session-log.md",
    )
)

hiddenimports = (
    collect_submodules("socratic_learn")
    + collect_submodules("learning_tutor")
    + collect_submodules("pypdf")
)

analysis = Analysis(
    [str(root / "socratic_learn" / "cli.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tests",
        "test",
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "wx",
    ],
    noarchive=False,
)
pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="socratic",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
