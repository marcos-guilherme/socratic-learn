from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests.validate_repository import main, validate, without_fenced_code

UNIVERSAL_REQUIRED_PATHS = (
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
    "LICENSE",
    "docs/universal-installation.md",
    "docs/launcher-adapters.md",
    "docs/manifest-reference.md",
    "docs/adding-an-adapter.md",
    "docs/superpowers/specs/2026-11-05-universal-distribution-design.md",
    "docs/superpowers/plans/2026-11-05-universal-distribution.md",
    "docs/superpowers/specs/2026-11-05-socratic-learn-rename-design.md",
    "docs/superpowers/plans/2026-11-05-socratic-learn-rename.md",
    ".github/workflows/native-python.yml",
)
RELEASE_REQUIRED_PATHS = (
    "pyproject.toml",
    "release-manifest.schema.json",
    "socratic-learn.spec",
    "scripts/install.ps1",
    "scripts/install.sh",
    ".github/workflows/release.yml",
)

CURRICULUM_FIELDS = (
    "Outcome",
    "Prerequisites",
    "Concepts",
    "Evidence",
    "Application",
)
CURRICULUM_HEADING_RE = re.compile(
    r"^### (?P<identifier>[a-z0-9]+(?:-[a-z0-9]+)*) — (?P<title>\S.*)$",
    re.MULTILINE,
)
CURRICULUM_FIELD_RE = re.compile(
    r"^- (?P<name>Outcome|Prerequisites|Concepts|Evidence|Application):"
    r"[ \t]*(?P<value>\S.*)$",
    re.MULTILINE,
)
ADAPTER_ENTRIES = (
    ".cursor/skills/socratic-learn/SKILL.md",
    "adapters/cursor/README.md",
    "adapters/claude-code/CLAUDE.md",
    "adapters/claude-code/README.md",
    "adapters/pi/skills/socratic-learn/SKILL.md",
    "adapters/pi/README.md",
)
ADAPTER_SKILLS = (
    ".cursor/skills/socratic-learn/SKILL.md",
    "adapters/pi/skills/socratic-learn/SKILL.md",
    "adapters/pi/skills/socratic-learn/SKILL.project.md.template",
    "socratic_learn/templates/cursor-skill.md",
    "socratic_learn/templates/pi-skill.md",
)
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s]+)(?:\s+[^)]*)?\)")
ROOT_CLAUDE_LOADER_RE = re.compile(
    r"<!-- root-loader:start -->\s*```markdown\n(.*?)\n```"
    r"\s*<!-- root-loader:end -->",
    re.DOTALL,
)
PI_PROJECT_TEMPLATE = "adapters/pi/skills/socratic-learn/SKILL.project.md.template"
PI_PACKAGE_DIRECTORY = ".socratic-learn"
SESSION_H2_HEADINGS = (
    "## Outcome",
    "## Diagnostic evidence",
    "## Approved dependency path",
    "## Concepts established",
    "## Application evidence",
    "## Remaining gaps",
    "## Next step",
    "## Sources",
)
README_HEADINGS = (
    "## What Socratic Learn provides",
    "## Quick start",
    "## How a learning session works",
    "## Install for your agent",
    "## Commands",
    "## Private learner state",
    "## Security and recovery",
    "## Migrating from Learning Tutor",
    "## Development",
    "## Limitations",
    "## License",
)
README_WORKSPACE_COMMANDS = (
    "Copy-Item -Recurse workspace.example\\* workspace",
    "cp -R workspace.example/. workspace/",
)
README_LAUNCHER_COMMANDS = (
    "socratic",
    'socratic "I want to learn linear algebra"',
    "socratic --agent pi",
    "socratic --here",
    "socratic update",
    "socratic uninstall",
    "pipx install socratic-learn",
)


def parse_curriculum_nodes(text: str) -> list[tuple[str, dict[str, str]]]:
    headings = list(CURRICULUM_HEADING_RE.finditer(text))
    nodes: list[tuple[str, dict[str, str]]] = []
    for index, heading in enumerate(headings):
        block_end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        fields = {
            match.group("name"): match.group("value").strip()
            for match in CURRICULUM_FIELD_RE.finditer(
                text, heading.end(), block_end
            )
        }
        nodes.append((heading.group("identifier"), fields))
    return nodes


def parse_prerequisite_ids(value: str) -> set[str]:
    return {identifier.strip() for identifier in value.split(",")}


class RepositoryValidationTests(unittest.TestCase):
    def tracked_copy(self, destination: Path) -> None:
        source_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=source_root,
            check=True,
            capture_output=True,
        )
        for raw_relative in result.stdout.split(b"\0"):
            if not raw_relative:
                continue
            relative = raw_relative.decode("utf-8")
            source = source_root / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def make_root(
        self, nested_under_workspace: bool = False
    ) -> tuple[TemporaryDirectory, Path]:
        temp = TemporaryDirectory()
        root = Path(temp.name)
        if nested_under_workspace:
            root = root / "workspace" / "repository"
            root.mkdir(parents=True)
        (root / ".gitignore").write_text(
            "workspace/*\n!workspace/.gitkeep\n__pycache__/\n*.py[cod]\n",
            encoding="utf-8",
        )
        (root / ".gitattributes").write_text(
            "dist/* text eol=lf\n",
            encoding="utf-8",
        )
        for relative in (
            "README.md",
            "AGENTS.md",
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
            PI_PROJECT_TEMPLATE,
            "adapters/pi/README.md",
            "workspace.example/learner-profile.md",
            "workspace.example/learning-goal.md",
            "workspace.example/progress.md",
            "workspace.example/sessions/2026-01-15-example.md",
            "workspace/.gitkeep",
            *UNIVERSAL_REQUIRED_PATHS,
            *RELEASE_REQUIRED_PATHS,
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# file\n", encoding="utf-8")
        source_root = Path(__file__).resolve().parents[1]
        for relative in (
            "README.md",
            *UNIVERSAL_REQUIRED_PATHS,
            *RELEASE_REQUIRED_PATHS,
            "core/pedagogy.md",
            "core/session-protocol.md",
            "core/assessment.md",
            "core/evidence-policy.md",
            "curricula/mathematics/map.md",
            "curricula/ai/map.md",
        ):
            shutil.copy2(source_root / relative, root / relative)
        skill = (
            "---\n"
            "name: socratic-learn\n"
            "description: Conducts diagnostic, evidence-aware learning "
            "sessions for any subject or skill.\n"
            "---\n\n# Socratic Learn\n"
        )
        for relative in ADAPTER_SKILLS:
            (root / relative).write_text(skill, encoding="utf-8")
        (root / "AGENTS.md").write_text(
            "# Agent Entry\n\n"
            "- [Pedagogy](core/pedagogy.md)\n"
            "- [Session protocol](core/session-protocol.md)\n"
            "- [Assessment](core/assessment.md)\n"
            "- [Evidence policy](core/evidence-policy.md)\n",
            encoding="utf-8",
        )
        return temp, root

    def test_minimal_valid_repository_passes(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        self.assertEqual([], validate(root))

    def test_legacy_package_rejects_implementation_modules(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        legacy_module = root / "learning_tutor/install.py"
        legacy_module.write_text("raise RuntimeError\n", encoding="utf-8")

        self.assertIn(
            "Legacy package contains implementation module: "
            "learning_tutor/install.py",
            validate(root),
        )

    def test_validator_rejects_missing_posix_threat_model(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        readme = root / "README.md"
        readme.write_text("# Portable AI Learning Environment\n", encoding="utf-8")

        errors = validate(root)

        self.assertTrue(
            any(
                "POSIX same-principal threat model" in error
                and "README.md" in error
                for error in errors
            ),
            errors,
        )

    def test_runtime_and_acceptance_language_stays_scoped(self) -> None:
        root = Path(__file__).resolve().parents[1]
        install = (root / "socratic_learn/install.py").read_text(encoding="utf-8")
        design = (
            root / "docs/superpowers/specs/2026-11-05-universal-distribution-design.md"
        ).read_text(encoding="utf-8")

        self.assertNotIn("no external data was deleted", install.lower())
        self.assertIn(
            "must not knowingly overwrite modified or unowned files",
            design.lower(),
        )
        self.assertIn("hostile same-principal mutation", design.lower())

    def test_agents_entry_references_every_core_document(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        required = (
            "core/pedagogy.md",
            "core/session-protocol.md",
            "core/assessment.md",
            "core/evidence-policy.md",
        )
        text = (root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(all(target in text for target in required))

    def test_readme_provides_complete_onboarding_contract(self) -> None:
        root = Path(__file__).resolve().parents[1]
        readme = root / "README.md"
        self.assertTrue(readme.exists(), "README.md must exist")
        text = readme.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Socratic Learn\n"))
        self.assertIn(
            "A portable, evidence-aware Socratic protocol for learning anything.",
            text,
        )
        self.assertIn("any subject or skill", text.lower())
        self.assertIn("starter curricula", text.lower())
        headings = tuple(
            line for line in text.splitlines() if line.startswith("## ")
        )
        headings_with_extra = (
            headings[:1] + ("## Optional additional guidance",) + headings[1:]
        )
        remaining_headings = iter(headings_with_extra)
        for required_heading in README_HEADINGS:
            with self.subTest(heading=required_heading):
                self.assertIn(
                    required_heading,
                    remaining_headings,
                    f"Missing or out-of-order README heading: {required_heading}",
                )
        for command in README_WORKSPACE_COMMANDS:
            with self.subTest(command=command):
                self.assertIn(command, text)

    def test_readme_provides_public_launcher_onboarding(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "README.md").read_text(encoding="utf-8")
        normalized = " ".join(text.split()).lower()

        for command in README_LAUNCHER_COMMANDS:
            with self.subTest(command=command):
                self.assertIn(command, text)
        for clause in (
            "no repository clone",
            "does not store provider credentials",
            "shell history",
            "unsigned",
            "smartscreen",
            "gatekeeper",
            "pi, claude code, and antigravity",
            "cursor remains a project integration",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, normalized)

    def test_launcher_and_distribution_docs_define_public_contracts(self) -> None:
        root = Path(__file__).resolve().parents[1]
        launcher_path = root / "docs/launcher-adapters.md"
        self.assertTrue(launcher_path.is_file(), "Missing docs/launcher-adapters.md")
        launcher = launcher_path.read_text(encoding="utf-8")
        launcher_normalized = " ".join(launcher.split()).lower()
        for clause in (
            "executable detection",
            "exact command construction",
            "protocol delivery",
            "inherits authentication",
            "inherits terminal",
            "fake executable",
        ):
            with self.subTest(document="launcher adapters", clause=clause):
                self.assertIn(clause, launcher_normalized)
        for executable in ("`pi`", "`claude`", "`agy`"):
            self.assertIn(executable, launcher)

        installation = (
            root / "docs/universal-installation.md"
        ).read_text(encoding="utf-8")
        installation_normalized = " ".join(installation.split()).lower()
        for clause in (
            "x86-64",
            "sha-256",
            "unsigned",
            "rollback",
            "pipx upgrade socratic-learn",
            "pipx uninstall socratic-learn",
            "preserves learner data",
        ):
            with self.subTest(document="installation", clause=clause):
                self.assertIn(clause, installation_normalized)

    def test_validator_rejects_narrow_readme_positioning(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        readme = root / "README.md"
        text = readme.read_text(encoding="utf-8")
        text = text.replace(
            "A portable, evidence-aware Socratic protocol for learning anything.",
            "A portable Socratic learning protocol for mathematics and AI.",
        ).replace("any subject or skill", "mathematics and AI")
        readme.write_text(text, encoding="utf-8")

        self.assertIn(
            "Narrow product positioning in README.md",
            validate(root),
        )

    def test_validator_rejects_missing_public_launcher_contract(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        readme = root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8").replace(
                "Socratic Learn does not store provider credentials",
                "Authentication is handled elsewhere",
            ),
            encoding="utf-8",
        )

        self.assertIn(
            "README.md is missing public launcher onboarding",
            validate(root),
        )

    def test_validator_rejects_incomplete_launcher_adapter_contract(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        launcher = root / "docs/launcher-adapters.md"
        launcher.write_text("# Launcher Adapters\n", encoding="utf-8")

        self.assertIn(
            "docs/launcher-adapters.md is missing launcher adapter contracts",
            validate(root),
        )

    def test_repository_uses_mit_license(self) -> None:
        root = Path(__file__).resolve().parents[1]
        license_text = (root / "LICENSE").read_text(encoding="utf-8")

        self.assertTrue(license_text.startswith("MIT License\n"))
        self.assertIn("Copyright (c) 2026 Marcos Guilherme", license_text)

    def test_readme_pi_onboarding_points_to_install_assets(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "README.md").read_text(encoding="utf-8")
        linked_targets = set(MARKDOWN_LINK_RE.findall(text))

        self.assertIn("adapters/pi/README.md", linked_targets)
        self.assertIn(PI_PROJECT_TEMPLATE, linked_targets)
        self.assertNotIn(
            "adapters/pi/skills/socratic-learn/SKILL.md",
            linked_targets,
        )

    def test_adapter_skills_advertise_universal_learning(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for relative in ADAPTER_SKILLS:
            with self.subTest(skill=relative):
                text = (root / relative).read_text(encoding="utf-8")
                frontmatter = text.split("---\n", 2)[1].lower()
                self.assertIn("name: socratic-learn", frontmatter)
                for term in (
                    "any subject or skill",
                    "diagnostic",
                    "evidence-aware",
                    "learning sessions",
                ):
                    self.assertIn(term, frontmatter)
                self.assertNotIn(
                    "mathematics and ai learning sessions",
                    frontmatter,
                )

    def test_validator_rejects_narrow_skill_positioning(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        path = root / ".cursor/skills/socratic-learn/SKILL.md"
        text = path.read_text(encoding="utf-8").replace(
            "for any subject or skill",
            "for mathematics and AI",
        )
        path.write_text(text, encoding="utf-8")

        self.assertIn(
            "Narrow product positioning in "
            ".cursor/skills/socratic-learn/SKILL.md",
            validate(root),
        )

    def test_every_adapter_entry_links_session_and_evidence_core(self) -> None:
        root = Path(__file__).resolve().parents[1]
        required_targets = {
            (root / "core/session-protocol.md").resolve(),
            (root / "core/evidence-policy.md").resolve(),
        }
        for relative in ADAPTER_ENTRIES:
            with self.subTest(adapter=relative):
                path = root / relative
                text = without_fenced_code(path.read_text(encoding="utf-8"))
                linked_targets = {
                    (path.parent / target).resolve()
                    for target in MARKDOWN_LINK_RE.findall(text)
                }
                self.assertTrue(
                    required_targets <= linked_targets,
                    f"{relative} must link both canonical protocol files",
                )
                self.assertTrue(
                    all(target.exists() for target in linked_targets),
                    f"{relative} contains a broken relative link",
                )

    def test_documented_root_claude_loader_references_resolve(self) -> None:
        root = Path(__file__).resolve().parents[1]
        readme = (root / "adapters/claude-code/README.md").read_text(
            encoding="utf-8"
        )
        match = ROOT_CLAUDE_LOADER_RE.search(readme)
        self.assertIsNotNone(match, "Missing documented root CLAUDE.md loader")
        snippet = match.group(1)
        linked_targets = {
            (root / target).resolve()
            for target in MARKDOWN_LINK_RE.findall(snippet)
        }
        required_targets = {
            (root / relative).resolve()
            for relative in (
                "AGENTS.md",
                "core/pedagogy.md",
                "core/session-protocol.md",
                "core/assessment.md",
                "core/evidence-policy.md",
            )
        }
        self.assertTrue(
            required_targets <= linked_targets,
            "Root loader must link the universal entry and canonical core",
        )
        self.assertTrue(
            all(target.exists() for target in linked_targets),
            "Root loader contains a reference that does not resolve from root",
        )
        self.assertIn("`workspace/`", snippet)
        self.assertTrue((root / "workspace").is_dir())

    def test_documented_pi_project_install_resolves_every_local_link(self) -> None:
        source_root = Path(__file__).resolve().parents[1]
        template = source_root / PI_PROJECT_TEMPLATE
        self.assertTrue(template.exists(), "Missing Pi project-install skill template")

        with TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            destination = project / ".pi/skills/socratic-learn/SKILL.md"
            destination.parent.mkdir(parents=True)
            shutil.copy2(template, destination)
            package = project / PI_PACKAGE_DIRECTORY
            package.mkdir()
            for relative in (
                "AGENTS.md",
                "core",
                "curricula",
            ):
                source = source_root / relative
                target = package / relative
                if source.is_dir():
                    shutil.copytree(source, target)
                else:
                    shutil.copy2(source, target)

            text = destination.read_text(encoding="utf-8")
            linked_targets = {
                (destination.parent / target).resolve()
                for target in MARKDOWN_LINK_RE.findall(text)
            }
            self.assertTrue(linked_targets, "Installed Pi skill must contain links")
            self.assertTrue(
                all(target.exists() for target in linked_targets),
                "Installed Pi skill contains a local link that does not resolve",
            )

    def test_pi_installation_is_namespaced_and_collision_safe(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "adapters/pi/README.md").read_text(encoding="utf-8")
        powershell = re.search(
            r"```powershell\n(?P<body>.*?)\n```",
            text,
            re.DOTALL,
        )
        posix = re.search(r"```sh\n(?P<body>.*?)\n```", text, re.DOTALL)
        self.assertIsNotNone(powershell)
        self.assertIsNotNone(posix)

        command_blocks = {
            "PowerShell": powershell.group("body"),
            "POSIX": posix.group("body"),
        }
        for shell, commands in command_blocks.items():
            with self.subTest(shell=shell):
                self.assertIn(PI_PACKAGE_DIRECTORY, commands)
                self.assertRegex(commands, r"(?i)(test-path|\[\s+-e\s+)")
                self.assertRegex(commands, r"(?i)(throw|exit\s+1)")
                self.assertNotRegex(
                    commands,
                    r"(?im)(copy-item|cp)\s+.*AGENTS\.md\s+.*\$project[/\"']?\s*$",
                )

        visible = without_fenced_code(text).lower()
        self.assertIn("agents.md", visible)
        self.assertRegex(visible, r"does not (?:overwrite|write to)")
        self.assertIn("manual", visible)
        self.assertIn(".socratic-learn/AGENTS.md", text)

    def test_pi_installation_aborts_for_preexisting_skill_directory(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "adapters/pi/README.md").read_text(encoding="utf-8")
        powershell = re.search(
            r"```powershell\n(?P<body>.*?)\n```",
            text,
            re.DOTALL,
        ).group("body")
        posix = re.search(r"```sh\n(?P<body>.*?)\n```", text, re.DOTALL).group(
            "body"
        )

        with TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            skill_directory = project / ".pi/skills/socratic-learn"
            skill_directory.mkdir(parents=True)
            self.assertTrue(skill_directory.is_dir())
            self.assertFalse((skill_directory / "SKILL.md").exists())

        powershell_first_mutation = min(
            powershell.index("New-Item"),
            powershell.index("Copy-Item"),
        )
        for check in (
            "if (Test-Path $PackageDirectory)",
            "if (Test-Path $SkillDirectory)",
        ):
            with self.subTest(shell="PowerShell", check=check):
                self.assertGreaterEqual(powershell.find(check), 0)
                self.assertLess(powershell.index(check), powershell_first_mutation)

        posix_first_mutation = min(posix.index("mkdir"), posix.index("cp "))
        for check in (
            'if [ -e "$package_dir" ]',
            'if [ -e "$skill_dir" ]',
        ):
            with self.subTest(shell="POSIX", check=check):
                self.assertGreaterEqual(posix.find(check), 0)
                self.assertLess(posix.index(check), posix_first_mutation)

        for shell, commands in (("PowerShell", powershell), ("POSIX", posix)):
            with self.subTest(shell=shell, invariant="no removals"):
                self.assertNotRegex(commands, r"(?im)(remove-item|rm\s+-r)")

    def test_pedagogy_defines_responsive_socratic_dialogue(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "core/pedagogy.md").read_text(encoding="utf-8").lower()
        start = "## responsive socratic dialogue"
        end = "## active application"
        self.assertIn(start, text, "Missing canonical Socratic section")
        self.assertIn(end, text, "Missing section boundary after Socratic contract")
        section = text.split(start, 1)[1].split(end, 1)[0]
        section = " ".join(section.split())
        self.assertIn("across subjects and skills", section)
        self.assertNotIn("for mathematics and ai, useful probes", section)

        cycle = (
            "receive an answer or claim",
            "probe that answer's reasoning",
            "surface a contradiction or gap (aporia)",
            "ask the learner to refine the answer",
            "repeat from the refinement",
        )
        previous = -1
        for step in cycle:
            with self.subTest(contract="responsive cycle", step=step):
                position = section.find(step)
                self.assertGreater(
                    position,
                    previous,
                    f"Missing or out-of-order Socratic cycle step: {step}",
                )
                previous = position

        question_families = {
            "clarification": "clarification of meaning or examples",
            "assumptions": "assumptions required by the claim",
            "reasons and evidence": "reasons and evidence supporting or refuting it",
            "implications and consequences": (
                "implications and consequences if it holds"
            ),
            "perspectives": "perspectives or alternative approaches",
            "metacognition": (
                "metacognition about why the question matters "
                "or how it should be asked"
            ),
        }
        for family, clause in question_families.items():
            with self.subTest(contract="question family", family=family):
                self.assertIn(
                    clause,
                    section,
                    f"Missing Socratic question family: {family}",
                )

        contracts = {
            "quiz versus dialogue": (
                "a single question can be a quiz",
                "each question derives from the learner's preceding answer",
                "never from a fixed script",
            ),
            "deep listening": (
                "practice deep listening",
                "interpret the learner's actual reasoning",
            ),
            "grounded in demonstrated knowledge": (
                "knowledge the learner has already demonstrated",
            ),
            "active return after exposition": (
                "after exposition",
                "active application or an active question",
            ),
            "wait and answer restraint": (
                "allow wait time and silence",
                "restrain the impulse to give an answer",
            ),
            "safe and humble inquiry": (
                "collaborative and safe for mistakes",
                "never adversarial or a gotcha",
                "tutor and learner",
                "intellectual humility",
            ),
            "internalized self-questioning": (
                "question families become internal habits",
                "independent self-questioner",
            ),
            "mode selection limits": (
                "next step is discoverable",
                "use direct exposition",
                "information is not deducible",
                "inappropriate cognitive load",
            ),
            "subject-neutral probes": (
                "across subjects and skills",
                "why does this work?",
                "which assumption is necessary?",
                "what evidence would refute the claim?",
                "what changes when this condition varies?",
                "how does another approach compare?",
                "domain-specific evidence rules",
                "mathematical classification and hypothesis rules",
            ),
        }
        for contract, clauses in contracts.items():
            for clause in clauses:
                with self.subTest(contract=contract, clause=clause):
                    self.assertIn(
                        clause,
                        section,
                        f"Missing {contract} contract clause: {clause}",
                    )

    def test_session_contract_template_and_example_share_exact_headings(self) -> None:
        root = Path(__file__).resolve().parents[1]
        contract_text = (root / "core/session-protocol.md").read_text(
            encoding="utf-8"
        )
        contract_block = contract_text.split("```markdown", 1)[1].split("```", 1)[0]
        sources = {
            "canonical contract": contract_block,
            "session template": (root / "templates/session-log.md").read_text(
                encoding="utf-8"
            ),
            "example session": (
                root / "workspace.example/sessions/2026-01-15-example.md"
            ).read_text(encoding="utf-8"),
        }

        for source, text in sources.items():
            actual = tuple(line for line in text.splitlines() if line.startswith("## "))
            with self.subTest(source=source):
                self.assertEqual(SESSION_H2_HEADINGS, actual)

        placeholder_sources = {
            "canonical contract": contract_block,
            "session template": sources["session template"],
        }
        for source, text in placeholder_sources.items():
            with self.subTest(source=source, heading="placeholder H1"):
                self.assertEqual(
                    "# Session: YYYY-MM-DD — Topic",
                    text.strip().splitlines()[0],
                )

        example_h1 = sources["example session"].splitlines()[0]
        self.assertRegex(
            example_h1,
            r"^# Session: \d{4}-\d{2}-\d{2} — \S.*$",
        )

    def test_progress_template_preserves_required_headings(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "templates/progress.md").read_text(encoding="utf-8")
        for heading in (
            "## Demonstrated",
            "## Developing",
            "## Next evidence needed",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, text, f"Missing heading: {heading}")

    def test_curriculum_nodes_use_shared_schema(self) -> None:
        root = Path(__file__).resolve().parents[1]
        expected_nodes = {
            "curricula/mathematics/map.md": {
                "algebraic-reasoning",
                "functions-and-graphs",
                "exponentials-and-logarithms",
                "limits-and-change",
                "derivatives",
                "vectors-and-dot-products",
                "matrices-and-linear-maps",
                "probability-models",
                "random-variables",
                "optimization",
                "math-for-machine-learning",
            },
            "curricula/ai/map.md": {
                "supervised-learning",
                "loss-and-generalization",
                "gradient-based-learning",
                "neural-networks",
                "tensor-frameworks",
                "attention",
                "transformers",
                "language-models",
                "evaluation",
                "framework-experimentation",
            },
        }
        for relative, expected in expected_nodes.items():
            with self.subTest(curriculum=relative):
                path = root / relative
                self.assertTrue(path.exists(), f"Missing curriculum map: {relative}")
                nodes = parse_curriculum_nodes(path.read_text(encoding="utf-8"))
                identifiers = [identifier for identifier, _ in nodes]
                self.assertEqual(expected, set(identifiers))
                self.assertEqual(
                    len(identifiers),
                    len(set(identifiers)),
                    f"Duplicate curriculum node identifier in {relative}",
                )
                for identifier, fields in nodes:
                    self.assertEqual(
                        set(CURRICULUM_FIELDS),
                        set(fields),
                        f"Invalid fields for {identifier} in {relative}",
                    )

    def test_ai_softmax_and_log_loss_link_exponentials_and_logarithms(self) -> None:
        root = Path(__file__).resolve().parents[1]
        path = root / "curricula/ai/map.md"
        nodes = dict(parse_curriculum_nodes(path.read_text(encoding="utf-8")))
        target = "../mathematics/map.md#exponentials-and-logarithms"

        for identifier in ("attention", "language-models"):
            with self.subTest(node=identifier):
                self.assertIn(target, nodes[identifier]["Concepts"])

    def test_curriculum_prerequisites_reference_local_nodes(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "curricula/mathematics/map.md",
            "curricula/ai/map.md",
        ):
            with self.subTest(curriculum=relative):
                path = root / relative
                self.assertTrue(path.exists(), f"Missing curriculum map: {relative}")
                nodes = parse_curriculum_nodes(path.read_text(encoding="utf-8"))
                identifiers = {identifier for identifier, _ in nodes}
                for identifier, fields in nodes:
                    prerequisites = {
                        value.strip()
                        for value in fields["Prerequisites"].split(",")
                    }
                    unknown = prerequisites - identifiers - {"none"}
                    self.assertEqual(
                        set(),
                        unknown,
                        f"Unknown prerequisites for {identifier} in {relative}",
                    )

    def test_general_ai_evaluation_does_not_require_language_models(self) -> None:
        root = Path(__file__).resolve().parents[1]
        path = root / "curricula/ai/map.md"
        nodes = dict(parse_curriculum_nodes(path.read_text(encoding="utf-8")))
        prerequisites = parse_prerequisite_ids(
            nodes["evaluation"]["Prerequisites"]
        )

        self.assertEqual(
            {"loss-and-generalization", "supervised-learning"},
            parse_prerequisite_ids(
                " loss-and-generalization, supervised-learning "
            ),
        )
        self.assertIn("loss-and-generalization", prerequisites)
        self.assertNotIn("language-models", prerequisites)

    def test_missing_required_paths_fail_by_category(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        cases = (
            ("core entry", "AGENTS.md"),
            ("adapter readme", "adapters/claude-code/README.md"),
            ("adapter readme", "adapters/pi/README.md"),
            ("adapter artifact", PI_PROJECT_TEMPLATE),
            ("filled example", "workspace.example/learner-profile.md"),
            ("filled example", "workspace.example/learning-goal.md"),
            ("filled example", "workspace.example/progress.md"),
            (
                "filled example",
                "workspace.example/sessions/2026-01-15-example.md",
            ),
        )
        for category, relative in cases:
            with self.subTest(category=category, path=relative):
                path = root / relative
                original = path.read_text(encoding="utf-8")
                path.unlink()
                self.assertIn(
                    f"Missing required path: {relative}",
                    validate(root),
                )
                path.write_text(original, encoding="utf-8")

    def test_universal_package_artifacts_and_docs_are_required(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        for relative in UNIVERSAL_REQUIRED_PATHS:
            (root / relative).unlink()

        errors = validate(root)

        for relative in UNIVERSAL_REQUIRED_PATHS:
            with self.subTest(path=relative):
                self.assertIn(f"Missing required path: {relative}", errors)

    def test_native_release_automation_contract(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for relative in RELEASE_REQUIRED_PATHS:
            with self.subTest(path=relative):
                self.assertTrue((root / relative).is_file(), f"Missing {relative}")

        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(
            'socratic = "socratic_learn.cli:entry_point"',
            pyproject,
        )

        release = (root / ".github/workflows/release.yml").read_text(
            encoding="utf-8"
        )
        for value in (
            'tags: ["v*"]',
            "workflow_dispatch:",
            "windows-latest",
            "ubuntu-latest",
            "macos-13",
            "python-version: \"3.11\"",
            "python -m unittest discover",
            "python tests/validate_repository.py",
            "python -m PyInstaller socratic-learn.spec",
            "socratic --version",
            "actions/download-artifact@v4",
            "hashlib.sha256",
            "release-manifest.schema.json",
            "'  '",
            "pypa/gh-action-pypi-publish@release/v1",
            "environment: pypi",
            "id-token: write",
            "contents: write",
            "scripts/install.ps1",
            "scripts/install.sh",
        ):
            with self.subTest(value=value):
                self.assertIn(value, release)
        self.assertLess(
            release.index("python -m unittest discover"),
            release.index("python -m PyInstaller socratic-learn.spec"),
        )
        publish_gate = (
            "if: github.event_name == 'push' && "
            "startsWith(github.ref, 'refs/tags/v')"
        )
        self.assertEqual(2, release.count(publish_gate))
        pypi = release.split("  publish-pypi:", 1)[1]
        self.assertIn("needs: [python-package, native, manifest]", pypi)
        self.assertIn("permissions:\n  contents: read", release)
        self.assertEqual(1, release.count("contents: write"))
        self.assertIn("github.ref_name", release)
        self.assertIn("__version__", release)

        normal = (root / ".github/workflows/native-python.yml").read_text(
            encoding="utf-8"
        )
        install = 'python -m pip install -e ".[build]"'
        wheel = "python -m build --wheel"
        tests = "python -m unittest discover"
        self.assertIn(install, normal)
        self.assertIn(wheel, normal)
        self.assertIn("socratic --version", normal)
        self.assertLess(normal.index(install), normal.index(tests))
        self.assertNotIn("PyInstaller", normal)

    def test_release_paths_are_required_by_validator(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        for relative in RELEASE_REQUIRED_PATHS:
            (root / relative).unlink()

        errors = validate(root)

        for relative in RELEASE_REQUIRED_PATHS:
            with self.subTest(path=relative):
                self.assertIn(f"Missing required path: {relative}", errors)

    def test_release_workflow_safety_is_validated(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        release.write_text(
            release.read_text(encoding="utf-8").replace(
                "permissions:\n  contents: read",
                "permissions:\n  contents: write",
                1,
            ),
            encoding="utf-8",
        )
        normal = root / ".github/workflows/native-python.yml"
        normal.write_text(
            normal.read_text(encoding="utf-8").replace(
                'python -m pip install -e ".[build]"',
                "python -m pip install -e .",
            ),
            encoding="utf-8",
        )

        errors = validate(root)

        self.assertIn("Release workflow must default to contents: read", errors)
        self.assertIn(
            "Native safety matrix must install .[build] before tests",
            errors,
        )

    def test_validator_rejects_unsafe_publish_gates_and_dependencies(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        strong_gate = (
            "if: github.event_name == 'push' && "
            "startsWith(github.ref, 'refs/tags/v')"
        )
        text = release.read_text(encoding="utf-8")
        text = text.replace(
            strong_gate,
            "if: startsWith(github.ref, 'refs/tags/v')",
        )
        before_pypi, pypi = text.split("  publish-pypi:", 1)
        pypi = pypi.replace(
            "needs: [python-package, native, manifest]",
            "needs: python-package",
            1,
        )
        text = before_pypi + "  publish-pypi:" + pypi
        release.write_text(text, encoding="utf-8")

        errors = validate(root)

        self.assertIn(
            "Release publishing must require a push event and version tag",
            errors,
        )
        self.assertIn(
            "PyPI publishing must wait for package, native, and manifest jobs",
            errors,
        )

    def test_native_ci_workflow_covers_required_platforms_and_checks(self) -> None:
        workflow = Path(__file__).resolve().parents[1] / (
            ".github/workflows/native-python.yml"
        )
        text = workflow.read_text(encoding="utf-8")

        for value in (
            "windows-latest",
            "ubuntu-latest",
            "macos-latest",
            "python-version: \"3.11\"",
            "python -m socratic_learn build",
            "python -m unittest discover",
            "python tests/validate_repository.py",
            '"install", "generic"',
            "--update",
            '"doctor", str(project)',
            "create_valid_legacy_install",
            "sys.path.insert(0, str(root))",
            '"git", "diff", "--check"',
            '"git", "status", "--porcelain"',
        ):
            with self.subTest(value=value):
                self.assertIn(value, text)

    def test_required_file_directory_masquerade_is_reported_clearly(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        relative = "dist/manifest.json"
        path = root / relative
        path.unlink()
        path.mkdir()

        errors = validate(root)

        self.assertIn(
            f"Required path is not a file: {relative} (found directory)",
            errors,
        )
        self.assertNotIn(f"Missing required path: {relative}", errors)

    def test_stale_distribution_is_detected_without_mutation(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.tracked_copy(root)
            bundle = root / "dist/socratic-learn.prompt.md"
            bundle.write_bytes(bundle.read_bytes() + b"stale\n")
            before = {
                path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in (root / "dist").iterdir()
            }

            errors = validate(root)

            after = {
                path.name: (path.read_bytes(), path.stat().st_mtime_ns)
                for path in (root / "dist").iterdir()
            }
            self.assertEqual(before, after)
            self.assertTrue(
                any(
                    "stale generated artifacts" in error
                    and "python -m socratic_learn build" in error
                    for error in errors
                )
            )

    def test_generated_bundle_header_and_manifest_paths_are_validated(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.tracked_copy(root)
            bundle = root / "dist/socratic-learn.prompt.md"
            bundle.write_bytes(
                bundle.read_bytes().replace(
                    b"# Socratic Learn\n",
                    b"# Wrong Header\n",
                    1,
                )
            )
            manifest_path = root / "dist/manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["sources"][0]["path"] = "C:/private/source.md"
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )

            errors = validate(root)

            self.assertTrue(any("expected header" in error for error in errors))
            self.assertTrue(any("relative POSIX path" in error for error in errors))

    def test_broken_relative_markdown_link_fails(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / "README.md").write_text("[Missing](missing.md)\n", encoding="utf-8")
        self.assertTrue(any("missing.md" in error for error in validate(root)))

    def test_fenced_code_is_ignored_for_links_and_private_markers(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        readme = root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\n```markdown\n[Missing](missing.md)\nPRIVATE_LEARNER_DATA\n```\n",
            encoding="utf-8",
        )
        self.assertEqual([], validate(root))

    def test_markdown_link_with_optional_title_passes(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / "guide.md").write_text("# Guide\n", encoding="utf-8")
        readme = root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8") + '\n[Guide](guide.md "Guide")\n',
            encoding="utf-8",
        )
        self.assertEqual([], validate(root))

    def test_invalid_skill_frontmatter_fails(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        skill = root / ".cursor/skills/socratic-learn/SKILL.md"
        skill.write_text("---\nname: Socratic Learn\n---\n", encoding="utf-8")
        self.assertTrue(any("frontmatter" in error for error in validate(root)))

    def test_unrelated_skill_name_fails_with_existing_diagnostic(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        skill = root / ".cursor/skills/socratic-learn/SKILL.md"
        skill.write_text(
            "---\n"
            "name: unrelated-skill\n"
            "description: Conducts structured learning sessions.\n"
            "---\n",
            encoding="utf-8",
        )
        self.assertIn(
            "Invalid skill frontmatter: .cursor/skills/socratic-learn/SKILL.md",
            validate(root),
        )

    def test_canonical_copy_in_adapter_fails(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        canonical = "A canonical paragraph long enough to identify duplicated guidance."
        (root / "core/pedagogy.md").write_text(
            f"<!-- canonical:start -->\n{canonical}\n<!-- canonical:end -->\n",
            encoding="utf-8",
        )
        (root / "adapters/cursor/README.md").write_text(canonical, encoding="utf-8")
        self.assertTrue(any("duplicates canonical" in error for error in validate(root)))

    def test_private_marker_outside_workspace_fails(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / "README.md").write_text("PRIVATE_LEARNER_DATA\n", encoding="utf-8")
        self.assertTrue(any("private learner" in error for error in validate(root)))

    def test_private_marker_inline_mention_passes(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        readme = root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\nThe PRIVATE_LEARNER_DATA marker identifies private records.\n",
            encoding="utf-8",
        )
        self.assertEqual([], validate(root))

    def test_workspace_exclusion_uses_path_relative_to_root(self) -> None:
        temp, root = self.make_root(nested_under_workspace=True)
        self.addCleanup(temp.cleanup)
        (root / "README.md").write_text("PRIVATE_LEARNER_DATA\n", encoding="utf-8")
        self.assertTrue(any("private learner" in error for error in validate(root)))

    def test_git_unavailable_in_repository_is_validation_error(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / ".git").mkdir()
        with patch(
            "tests.validate_repository.subprocess.run",
            side_effect=FileNotFoundError("git"),
        ):
            errors = validate(root)
        self.assertTrue(any("git ls-files unavailable" in error for error in errors))

    def test_git_ls_files_failure_is_validation_error(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / ".git").mkdir()
        failure = subprocess.CalledProcessError(
            128, ["git", "ls-files"], stderr="fatal: test failure"
        )
        with patch(
            "tests.validate_repository.subprocess.run", side_effect=failure
        ):
            errors = validate(root)
        self.assertTrue(any("git ls-files failed" in error for error in errors))

    def test_tracked_private_file_fails(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        private = root / "workspace/private.md"
        private.write_text("# Private\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(
            ["git", "add", "-f", "workspace/private.md"],
            cwd=root,
            check=True,
        )
        self.assertTrue(
            any("workspace/private.md" in error for error in validate(root))
        )

    def test_invalid_gitignore_fails(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / ".gitignore").write_text("workspace/*\n", encoding="utf-8")
        self.assertTrue(any(".gitignore" in error for error in validate(root)))

    def test_main_returns_zero_and_prints_success(self) -> None:
        output = StringIO()
        with patch("tests.validate_repository.validate", return_value=[]):
            with redirect_stdout(output):
                result = main()
        self.assertEqual(0, result)
        self.assertEqual("Repository validation passed.\n", output.getvalue())

    def test_main_returns_one_and_prints_each_error(self) -> None:
        output = StringIO()
        with patch(
            "tests.validate_repository.validate",
            return_value=["first problem", "second problem"],
        ):
            with redirect_stdout(output):
                result = main()
        self.assertEqual(1, result)
        self.assertEqual(
            "ERROR: first problem\nERROR: second problem\n", output.getvalue()
        )

    def test_validator_script_runs_from_repository_root(self) -> None:
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "tests/validate_repository.py"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("Repository validation passed.\n", result.stdout)

    def test_generated_distribution_is_checked_out_lf_only(self) -> None:
        root = Path(__file__).resolve().parents[1]
        attributes = root / ".gitattributes"
        self.assertTrue(attributes.is_file())
        rules = attributes.read_text(encoding="utf-8").splitlines()
        self.assertIn("dist/* text eol=lf", rules)

    def test_installation_docs_distinguish_managed_files_from_recovery_paths(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "docs/universal-installation.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(text.split())
        self.assertIn("receipt lists managed files", normalized)
        self.assertIn("not managed-file receipt entries", normalized)
        self.assertIn("After a successful install or update", normalized)
        self.assertIn("staging and backup directories are removed", normalized)
        self.assertIn("preserves partial published paths", normalized)


if __name__ == "__main__":
    unittest.main()
