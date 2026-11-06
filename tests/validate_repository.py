from __future__ import annotations

import ast
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
    "docs/launcher-adapters.md",
    "docs/manifest-reference.md",
    "docs/adding-an-adapter.md",
    "docs/superpowers/specs/2026-11-05-universal-distribution-design.md",
    "docs/superpowers/plans/2026-11-05-universal-distribution.md",
    "docs/superpowers/specs/2026-11-05-socratic-learn-rename-design.md",
    "docs/superpowers/plans/2026-11-05-socratic-learn-rename.md",
    ".github/workflows/native-python.yml",
    "pyproject.toml",
    "release-manifest.schema.json",
    "socratic-learn.spec",
    "scripts/install.ps1",
    "scripts/install.sh",
    ".github/workflows/release.yml",
    "docs/superpowers/plans/2026-11-06-one-command-learning-launcher.md",
)
SKILL_PATHS = (
    ".cursor/skills/socratic-learn/SKILL.md",
    "adapters/pi/skills/socratic-learn/SKILL.md",
)
POSITIONING_SKILL_PATHS = (
    ".cursor/skills/socratic-learn/SKILL.md",
    "adapters/pi/skills/socratic-learn/SKILL.md",
    "adapters/pi/skills/socratic-learn/SKILL.project.md.template",
    "socratic_learn/templates/cursor-skill.md",
    "socratic_learn/templates/pi-skill.md",
)
README_POSITIONING_REQUIREMENTS = (
    "A portable, evidence-aware Socratic protocol for learning anything.",
    "any subject or skill",
    "starter curricula",
)
README_LAUNCHER_REQUIREMENTS = (
    "socratic",
    'socratic "i want to learn linear algebra"',
    "socratic --agent pi",
    "socratic --here",
    "socratic update",
    "socratic uninstall",
    "pipx install socratic-learn",
    "no repository clone",
    "does not store provider credentials",
    "shell history",
    "unsigned",
    "smartscreen",
    "gatekeeper",
    "pi, claude code, and antigravity",
    "cursor remains a project integration",
)
NATIVE_RELEASE_CAVEAT = (
    "native installation is available only after github release v0.1.0 "
    "is published."
)
PYPI_RELEASE_CAVEAT = (
    "the pipx command is available only after socratic-learn 0.1.0 "
    "is published on pypi."
)
VERSIONED_INSTALLER_URLS = (
    "https://github.com/marcos-guilherme/socratic-learn/releases/download/"
    "v0.1.0/install.ps1",
    "https://github.com/marcos-guilherme/socratic-learn/releases/download/"
    "v0.1.0/install.sh",
)
README_ONBOARDING_ORDER = (
    *VERSIONED_INSTALLER_URLS,
    "pipx install socratic-learn",
    "\nsocratic\n",
    'socratic "i want to learn linear algebra"',
    "socratic --agent pi",
    "socratic --here",
)
UNSAFE_INSTALLER_PATTERNS = (
    re.compile(
        r"https?://raw[.]githubusercontent[.]com/"
        r"[^\s<>()`]+/main/",
        re.IGNORECASE,
    ),
    re.compile(
        r"https?://github[.]com/[^\s<>()`]+/(?:raw|blob)/main/"
        r"[^\s<>()`]*(?:install[.]ps1|install[.]sh)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"https?://github[.]com/[^\s<>()`]+/releases/latest/download/"
        r"[^\s<>()`]*(?:install[.]ps1|install[.]sh)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:irm|invoke-restmethod|iwr|invoke-webrequest)\b"
        r"[^\r\n|]*(?:\r?\n[ \t]*)?[|][ \t]*"
        r"(?:iex|invoke-expression)\b",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"\b(?:curl|wget)\b[^\r\n|]*"
        r"(?:\r?\n[ \t]*)?[|][ \t]*(?:sh|bash)\b",
        re.IGNORECASE | re.MULTILINE,
    ),
)
LAUNCHER_ADAPTER_REQUIREMENTS = (
    "executable detection",
    "exact command construction",
    "protocol delivery",
    "inherits authentication",
    "inherits terminal",
    "fake executable",
    "`pi`",
    "`claude`",
    "`agy`",
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
LOCAL_RELEASE_PLAN = (
    "docs/superpowers/plans/2026-11-06-one-command-learning-launcher.md"
)
LOCAL_PACKAGE_BUILD_COMMAND = "python -m build --outdir package-dist"
CANONICAL_DIST_FILES = {"manifest.json", "socratic-learn.prompt.md"}


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
            "python -m socratic_learn build"
        )
    return errors


def workflow_job(text: str, name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-z0-9-]+:\n|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(0) if match else ""


def workflow_matrix_include_entries(job: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    in_include = False
    for line in job.splitlines():
        if line == "        include:":
            in_include = True
            continue
        if not in_include:
            continue
        if line.startswith("          - "):
            if current is not None:
                entries.append(current)
            current = {}
            field = line[12:]
        elif current is not None and line.startswith("            "):
            field = line[12:]
        else:
            if current is not None:
                entries.append(current)
            break
        if ":" not in field:
            continue
        key, value = field.split(":", 1)
        value = value.split(" #", 1)[0].strip()
        current[key.strip()] = value.strip('"\'')
    else:
        if current is not None:
            entries.append(current)
    return entries


def workflow_steps(job: str) -> list[str]:
    return [
        match.group(0)
        for match in re.finditer(
            r"^      - .*?(?=^      - |^  [a-z0-9-]+:\n|\Z)",
            job,
            re.MULTILINE | re.DOTALL,
        )
    ]


def workflow_step(job: str, name: str) -> str:
    prefix = f"      - name: {name}\n"
    return next(
        (step for step in workflow_steps(job) if step.startswith(prefix)),
        "",
    )


def workflow_action_step(job: str, action: str) -> str:
    line = f"      - uses: {action}"
    return next(
        (step for step in workflow_steps(job) if step.splitlines()[0] == line),
        "",
    )


def workflow_action_input(step: str, name: str) -> str | None:
    lines = step.splitlines()
    try:
        start = lines.index("        with:") + 1
    except ValueError:
        return None
    prefix = f"          {name}: "
    for line in lines[start:]:
        if line.startswith(prefix):
            value = line[len(prefix) :].split(" #", 1)[0]
            return value.strip().strip('"\'')
        if line and not line.startswith("          "):
            break
    return None


def workflow_run_block(step: str) -> str:
    lines = step.splitlines()
    start = next(
        (
            index + 1
            for index, line in enumerate(lines)
            if re.fullmatch(r"        run: \|[+-]?", line)
        ),
        None,
    )
    if start is None:
        return ""
    body: list[str] = []
    for line in lines[start:]:
        if not line:
            body.append("")
        elif line.startswith("          "):
            body.append(line[10:])
        else:
            break
    return "\n".join(body)


def workflow_python_step_uses_literal_run_block(step: str) -> bool:
    return any(
        re.fullmatch(r"        run: \|[+-]?", line)
        for line in step.splitlines()
    )


def workflow_step_uses_python_shell(step: str) -> bool:
    return any(
        re.fullmatch(
            r"""        shell: +(?:python(?: +\{0\})?"""
            r"""|"python(?: \{0\})?"|'python(?: \{0\})?')"""
            r"(?: +(?:#.*)?)?",
            line,
        )
        for line in step.splitlines()
    )


def workflow_uses_run_shell_defaults(text: str) -> bool:
    mappings: list[tuple[int, str]] = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indentation = len(line) - len(line.lstrip(" "))
        while mappings and mappings[-1][0] >= indentation:
            mappings.pop()
        match = re.fullmatch(
            r" *(?P<key>[A-Za-z][A-Za-z0-9_-]*):(?P<value>.*)",
            line,
        )
        if match is None:
            continue
        key = match.group("key")
        if (
            key == "shell"
            and len(mappings) >= 2
            and [mapping[1] for mapping in mappings[-2:]]
            == ["defaults", "run"]
        ):
            return True
        value = match.group("value").strip()
        if not value or value.startswith("#"):
            mappings.append((indentation, key))
    return False


def workflow_python_assignment_matches(
    step: str,
    name: str,
    expected_expression: str,
) -> bool:
    try:
        statements = ast.parse(workflow_run_block(step)).body
        expected = ast.parse(expected_expression, mode="eval").body
    except SyntaxError:
        return False
    assignments = [
        statement.value
        for statement in statements
        if isinstance(statement, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == name
            for target in statement.targets
        )
    ]
    return len(assignments) == 1 and ast.dump(assignments[0]) == ast.dump(expected)


def workflow_python_tree(step: str) -> ast.Module | None:
    if not workflow_step_uses_python_shell(step):
        return None
    try:
        return ast.parse(workflow_run_block(step))
    except SyntaxError:
        return None


def workflow_python_local_imports(tree: ast.Module) -> list[ast.stmt]:
    imports: list[ast.stmt] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(
            alias.name == "socratic_learn"
            or alias.name.startswith("socratic_learn.")
            for alias in node.names
        ):
            imports.append(node)
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and (
                node.module == "socratic_learn"
                or node.module.startswith("socratic_learn.")
            )
        ):
            imports.append(node)
    return imports


def workflow_python_step_imports_local_package(step: str) -> bool:
    tree = workflow_python_tree(step)
    return tree is not None and bool(workflow_python_local_imports(tree))


def workflow_python_step_has_local_import_setup(step: str) -> bool:
    tree = workflow_python_tree(step)
    if tree is None:
        return False
    local_imports = workflow_python_local_imports(tree)
    if not local_imports:
        return True
    imported_at: dict[str, int] = {}
    required_setup = ast.parse("sys.path.insert(0, os.getcwd())").body[0]
    setup_at: list[int] = []
    for index, statement in enumerate(tree.body):
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.asname is None:
                    imported_at.setdefault(alias.name, index)
        if ast.dump(statement) == ast.dump(required_setup):
            setup_at.append(index)

    return (
        "os" in imported_at
        and "sys" in imported_at
        and len(setup_at) == 1
        and imported_at["os"] < setup_at[0]
        and imported_at["sys"] < setup_at[0]
        and tree.body[setup_at[0]].lineno
        < min(statement.lineno for statement in local_imports)
    )


def version_step_imports_local_package(step: str) -> bool:
    tree = workflow_python_tree(step)
    if tree is None or not workflow_python_step_has_local_import_setup(step):
        return False
    version_import_at: int | None = None
    for index, statement in enumerate(tree.body):
        if (
            isinstance(statement, ast.ImportFrom)
            and statement.module == "socratic_learn"
            and any(
                alias.name == "__version__" and alias.asname is None
                for alias in statement.names
            )
            and version_import_at is None
        ):
            version_import_at = index

    return version_import_at is not None


def validate_release_automation(root: Path) -> list[str]:
    errors: list[str] = []
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and (
        'socratic = "socratic_learn.cli:entry_point"'
        not in pyproject.read_text(encoding="utf-8")
    ):
        errors.append("pyproject.toml must map the socratic console entry point")

    spec = root / "socratic-learn.spec"
    if spec.is_file():
        spec_text = spec.read_text(encoding="utf-8")
        required_spec_terms = (
            "socratic_learn",
            "learning_tutor",
            "socratic_learn/data",
            "manifest.json",
            "socratic-learn.prompt.md",
            "learner-profile.md",
            "learning-goal.md",
            "progress.md",
            "session-log.md",
            'name="socratic"',
            "console=True",
            '"git", "diff", "--exit-code"',
            '"git", "status", "--porcelain"',
        )
        if not all(term in spec_text for term in required_spec_terms):
            errors.append("PyInstaller spec does not preserve the native build contract")

    release_path = root / ".github/workflows/release.yml"
    if release_path.is_file():
        release = release_path.read_text(encoding="utf-8")
        if "permissions:\n  contents: read" not in release:
            errors.append("Release workflow must default to contents: read")
        if release.count("contents: write") != 1:
            errors.append(
                "Release workflow must grant contents: write only to GitHub publishing"
            )
        required_release_terms = (
            'tags: ["v*"]',
            "workflow_dispatch:",
            "windows-latest",
            "ubuntu-latest",
            "actions/download-artifact@v4",
            "hashlib.sha256",
            "release-manifest.schema.json",
            "scripts/install.ps1",
            "scripts/install.sh",
        )
        if not all(term in release for term in required_release_terms):
            errors.append("Release workflow is missing required triggers or artifacts")
        if workflow_uses_run_shell_defaults(release):
            errors.append(
                "Release workflow must not use defaults.run.shell; "
                "Python steps must declare shell explicitly"
            )

        python_steps = [
            step
            for step in workflow_steps(release)
            if workflow_step_uses_python_shell(step)
        ]
        if any(
            not workflow_python_step_uses_literal_run_block(step)
            for step in python_steps
        ):
            errors.append(
                "Release shell: python steps must use a literal run block"
            )
        local_import_steps = [
            step
            for step in python_steps
            if workflow_python_step_imports_local_package(step)
        ]
        if any(
            not workflow_python_step_has_local_import_setup(step)
            for step in local_import_steps
        ):
            errors.append(
                "Every release shell: python step importing socratic_learn "
                "must add the checkout to sys.path before import"
            )

        native = workflow_job(release, "native")
        macos_entries = [
            entry
            for entry in workflow_matrix_include_entries(native)
            if entry.get("platform") == "macos"
        ]
        macos_matrix_valid = macos_entries == [
            {
                "os": "macos-15-intel",
                "platform": "macos",
                "extension": "",
            }
        ]
        if not macos_matrix_valid:
            errors.append(
                "Native macOS release matrix must use macos-15-intel "
                "with an empty extension"
            )

        rename_step = workflow_step(
            native,
            "Rename and smoke test socratic --version",
        )
        rename_valid = workflow_python_assignment_matches(
            rename_step,
            "destination",
            'root / "native-artifacts" / ('
            'f"socratic-{os.environ[\'RELEASE_PLATFORM\']}-x86_64" '
            'f"{os.environ[\'RELEASE_EXTENSION\']}"'
            ")",
        )
        upload_step = workflow_action_step(native, "actions/upload-artifact@v4")
        upload_valid = workflow_action_input(upload_step, "path") == (
            "native-artifacts/socratic-${{ matrix.platform }}"
            "-x86_64${{ matrix.extension }}"
        )
        if not rename_valid or not upload_valid:
            errors.append(
                "Native rename and upload steps must produce x86_64 artifacts"
            )

        suite = "python -m unittest discover"
        pyinstaller = "python -m PyInstaller socratic-learn.spec"
        if (
            not native
            or suite not in native
            or pyinstaller not in native
            or native.index(suite) > native.index(pyinstaller)
            or "python tests/validate_repository.py" not in native
            or "--version" not in native
        ):
            errors.append(
                "Every native release build must test and validate before PyInstaller"
            )

        manifest = workflow_job(release, "manifest")
        if (
            "actions/download-artifact@v4" not in manifest
            or "hashlib.sha256" not in manifest
            or manifest.index("actions/download-artifact@v4")
            > manifest.index("hashlib.sha256")
            or "path.stat().st_size" not in manifest
            or "separator = '  '" not in manifest
        ):
            errors.append(
                "Release manifest must hash downloaded native artifacts and use two spaces"
            )

        publish_gate = (
            "if: github.event_name == 'push' && "
            "startsWith(github.ref, 'refs/tags/v')"
        )
        github_publish = workflow_job(release, "publish-github")
        if (
            publish_gate not in github_publish
            or "contents: write" not in github_publish
        ):
            errors.append(
                "Release publishing must require a push event and version tag"
            )

        pypi_publish = workflow_job(release, "publish-pypi")
        if (
            publish_gate not in pypi_publish
            or "id-token: write" not in pypi_publish
            or "environment: pypi" not in pypi_publish
            or "pypa/gh-action-pypi-publish@release/v1" not in pypi_publish
        ):
            errors.append("PyPI publishing must use tag-only trusted publishing")
        if "needs: [python-package, native, manifest]" not in pypi_publish:
            errors.append(
                "PyPI publishing must wait for package, native, and manifest jobs"
            )

        version_job = workflow_job(release, "verify-version")
        if (
            "github.ref_name" not in release
            or "__version__" not in version_job
            or "refs/tags/v" not in version_job
        ):
            errors.append("Release tags must exactly match the package version")
        version_step = workflow_step(version_job, "Require an exact version tag")
        if not version_step_imports_local_package(version_step):
            errors.append(
                "Release version gate must add the checkout to sys.path before import"
            )

    normal_path = root / ".github/workflows/native-python.yml"
    if normal_path.is_file():
        normal = normal_path.read_text(encoding="utf-8")
        install = 'python -m pip install -e ".[build]"'
        suite = "python -m unittest discover"
        if (
            install not in normal
            or suite not in normal
            or normal.index(install) > normal.index(suite)
        ):
            errors.append("Native safety matrix must install .[build] before tests")
        if "python -m build --wheel" not in normal or "--version" not in normal:
            errors.append(
                "Native safety matrix must build and smoke-test an installed wheel"
            )
        if "PyInstaller" in normal:
            errors.append("Native safety matrix must not run PyInstaller")
    return errors


def validate_local_release_gate(root: Path) -> list[str]:
    errors: list[str] = []
    plan_path = root / LOCAL_RELEASE_PLAN
    if plan_path.is_file():
        commands = re.findall(
            r"(?m)^python -m build(?:[ \t].*)?$",
            plan_path.read_text(encoding="utf-8"),
        )
        if not commands or any(
            command != LOCAL_PACKAGE_BUILD_COMMAND for command in commands
        ):
            errors.append(
                "Active local release gates must use "
                f"{LOCAL_PACKAGE_BUILD_COMMAND}"
            )

    dist = root / "dist"
    if dist.is_dir():
        actual = {path.name for path in dist.iterdir()}
        if actual != CANONICAL_DIST_FILES:
            errors.append(
                "Canonical dist/ must contain exactly manifest.json and "
                "socratic-learn.prompt.md; package builds use package-dist/"
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

    readme = root / "README.md"
    if readme.is_file():
        readme_text = readme.read_text(encoding="utf-8")
        if not all(
            phrase.lower() in readme_text.lower()
            for phrase in README_POSITIONING_REQUIREMENTS
        ):
            errors.append("Narrow product positioning in README.md")
        normalized_readme = normalize(readme_text).lower()
        if not all(
            requirement in normalized_readme
            for requirement in README_LAUNCHER_REQUIREMENTS
        ):
            errors.append("README.md is missing public launcher onboarding")
        quick_start = readme_text.split("## Quick start", 1)
        quick_start_text = (
            quick_start[1].split("## How a learning session works", 1)[0]
            if len(quick_start) == 2
            else ""
        )
        order_positions = [
            quick_start_text.lower().find(marker)
            for marker in README_ONBOARDING_ORDER
        ]
        if (
            any(position < 0 for position in order_positions)
            or order_positions != sorted(order_positions)
        ):
            errors.append("README.md public onboarding is out of order")

    installer_docs = (
        (
            root / "README.md",
            "## Quick start",
            "## How a learning session works",
        ),
        (
            root / "docs/universal-installation.md",
            "## Normal installation",
            "## Native channel behavior",
        ),
    )
    for path, section_start, section_end in installer_docs:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        _before_section, separator, after_start = text.partition(section_start)
        section_text = (
            after_start.partition(section_end)[0]
            if separator
            else ""
        )
        normalized_text = normalize(section_text).lower()
        exact_urls_present = all(
            url in normalized_text for url in VERSIONED_INSTALLER_URLS
        )
        if not exact_urls_present:
            relative = path.relative_to(root).as_posix()
            errors.append(
                f"{relative} must use exact v0.1.0 PowerShell and POSIX "
                "installer URLs"
            )
        caveats_are_contextual = (
            NATIVE_RELEASE_CAVEAT in normalized_text
            and PYPI_RELEASE_CAVEAT in normalized_text
            and exact_urls_present
            and "pipx install socratic-learn" in normalized_text
            and normalized_text.index(NATIVE_RELEASE_CAVEAT)
            < min(
                normalized_text.index(url)
                for url in VERSIONED_INSTALLER_URLS
            )
            and normalized_text.index(PYPI_RELEASE_CAVEAT)
            < normalized_text.index("pipx install socratic-learn")
        )
        if not caveats_are_contextual:
            relative = path.relative_to(root).as_posix()
            errors.append(
                f"{relative} must condition native and PyPI instructions "
                "on publication"
            )
        if any(pattern.search(text) for pattern in UNSAFE_INSTALLER_PATTERNS):
            relative = path.relative_to(root).as_posix()
            errors.append(
                f"{relative} contains unsafe or mutable installer instructions"
            )

    launcher_adapters = root / "docs/launcher-adapters.md"
    if launcher_adapters.is_file():
        launcher_text = normalize(
            launcher_adapters.read_text(encoding="utf-8")
        ).lower()
        if not all(
            requirement in launcher_text
            for requirement in LAUNCHER_ADAPTER_REQUIREMENTS
        ):
            errors.append(
                "docs/launcher-adapters.md is missing launcher adapter contracts"
            )

    legacy_package = root / "learning_tutor"
    allowed_legacy_modules = {"__init__.py", "__main__.py"}
    if legacy_package.is_dir():
        for path in sorted(legacy_package.rglob("*.py")):
            relative = path.relative_to(root).as_posix()
            if (
                path.parent != legacy_package
                or path.name not in allowed_legacy_modules
            ):
                errors.append(
                    f"Legacy package contains implementation module: {relative}"
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

    for relative in POSITIONING_SKILL_PATHS:
        path = root / relative
        if not path.is_file():
            continue
        frontmatter = parse_frontmatter(path.read_text(encoding="utf-8"))
        if (
            frontmatter is None
            or "any subject or skill"
            not in frontmatter.get("description", "").lower()
        ):
            errors.append(f"Narrow product positioning in {relative}")

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
        if "/package-dist/" not in rules:
            errors.append(".gitignore must ignore /package-dist/")

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
    errors.extend(validate_release_automation(root))
    errors.extend(validate_local_release_gate(root))
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
