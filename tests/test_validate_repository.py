from contextlib import redirect_stdout
import errno
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

from tests.validate_repository import (
    UNSAFE_INSTALLER_PATTERNS,
    main,
    normalize,
    readme_opening_prose_paragraph,
    semantic_runtime_errors,
    validate,
    without_fenced_code,
)

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
    "docs/superpowers/plans/2026-11-06-one-command-learning-launcher.md",
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
    "## Learning route",
    "## Concepts established",
    "## Application evidence",
    "## Remaining gaps",
    "## Next step",
    "## Sources",
)
README_HEADINGS = (
    "## Why I built this",
    "## The method in 60 seconds",
    "## A compact example",
    "## How the system is structured",
    "## Research foundations",
    "## Engineering evidence",
    "## Evaluation status",
    "## Quick start",
    "## Supported hosts and project adapters",
    "## Privacy, security, and limitations",
    "## Development and documentation",
    "## License",
)
README_TAGLINE = (
    "A portable, evidence-aware Socratic protocol for learning any subject."
)
README_OPENING_PROMISE = "learn any subject"
README_UNFRIENDLY_DASHES = ("—", "–")
README_PORTFOLIO_REQUIREMENTS = (
    "I built Socratic Learn out of a recurring need in my work as an AI researcher",
    "objective → prerequisites → guided route → application → evidence",
    "Mahoney et al. (2023)",
    "Munshi et al. (2023)",
    "Borchers et al. (2025)",
    "van den Broek et al. (2025)",
    "Stogniy et al. (2020)",
    "Lee et al. (2025)",
    "https://doi.org/10.1016/j.tsc.2023.101422",
    "https://doi.org/10.1111/jcal.12761",
    "https://doi.org/10.1016/j.compedu.2025.105364",
    "https://doi.org/10.1016/j.learninstruc.2025.102196",
    "https://doi.org/10.1096/fasebj.2020.34.s1.04148",
    "https://doi.org/10.48550/arXiv.2509.16262",
    "three unchanged-protocol Antigravity sessions",
    "no pedagogy score was assigned",
    "evaluation/reports/2026-11-06-antigravity-baseline.md",
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
NATIVE_RELEASE_CAVEAT = (
    "Native installation is available only after GitHub Release v0.1.0 "
    "is published."
)
PYPI_RELEASE_CAVEAT = (
    "The pipx command is available only after socratic-learn 0.1.0 "
    "is published on PyPI."
)
VERSIONED_INSTALLER_URLS = (
    "https://github.com/marcos-guilherme/socratic-learn/releases/download/"
    "v0.1.0/install.ps1",
    "https://github.com/marcos-guilherme/socratic-learn/releases/download/"
    "v0.1.0/install.sh",
)


def requirement_pattern(requirement: str) -> re.Pattern[str]:
    words = re.split(r"[ \t\r\n]+", requirement.strip())
    return re.compile(
        r"[ \t\r\n]+".join(re.escape(word) for word in words)
    )


def replace_requirement_once(
    text: str,
    requirement: str,
    replacement: str,
) -> str:
    updated, count = requirement_pattern(requirement).subn(
        replacement,
        text,
        count=1,
    )
    if count != 1:
        raise AssertionError(
            f"Expected a whitespace-tolerant match for {requirement!r}"
        )
    return updated


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

    def require_symlink(
        self,
        link: Path,
        target: Path,
        *,
        target_is_directory: bool,
    ) -> None:
        try:
            link.symlink_to(
                target,
                target_is_directory=target_is_directory,
            )
        except OSError as error:
            if (
                getattr(error, "winerror", None) == 1314
                or error.errno in {errno.EACCES, errno.EPERM, errno.ENOSYS}
            ):
                self.skipTest(f"symbolic links are unavailable: {error}")
            raise

    def make_root(
        self, nested_under_workspace: bool = False
    ) -> tuple[TemporaryDirectory, Path]:
        temp = TemporaryDirectory()
        root = Path(temp.name)
        if nested_under_workspace:
            root = root / "workspace" / "repository"
            root.mkdir(parents=True)
        (root / ".gitignore").write_text(
            "workspace/*\n!workspace/.gitkeep\n__pycache__/\n*.py[cod]\n"
            "/package-dist/\n/.semantic-runs/\n",
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
            "evaluation/reports/2026-11-06-antigravity-baseline.md",
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
        tagline = f"**{README_TAGLINE}**"
        self.assertIn(tagline, text)
        opening = text.split("## Why I built this", 1)[0]
        first_prose_paragraph = readme_opening_prose_paragraph(opening)
        self.assertIn(
            README_OPENING_PROMISE,
            first_prose_paragraph.lower(),
        )
        for dash in README_UNFRIENDLY_DASHES:
            with self.subTest(dash=dash):
                self.assertNotIn(dash, text)
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
        normalized_text = " ".join(text.split())
        for requirement in README_PORTFOLIO_REQUIREMENTS:
            with self.subTest(portfolio_requirement=requirement):
                self.assertIn(" ".join(requirement.split()), normalized_text)
        self.assertIn("███████╗", text)
        self.assertNotRegex(text, r"!\[[^\]]*\]\(https?://")
        for command in README_WORKSPACE_COMMANDS:
            with self.subTest(command=command):
                self.assertIn(command, text)
        self.assertIn("**Preview the route.**", text)
        self.assertIn("start teaching automatically", normalized_text)
        self.assertIn("redirect at any time", normalized_text)
        self.assertNotIn("learner approval", normalized_text.lower())
        compact_example = text.split("## A compact example", 1)[1].split(
            "When the learner can reasonably work out the next step",
            1,
        )[0]
        normalized_example = " ".join(compact_example.split()).lower()
        self.assertNotIn("we choose a path", normalized_example)
        self.assertIn("i'll check the starting point first", normalized_example)
        self.assertIn(
            "i'll use your answer to set the route",
            normalized_example,
        )
        self.assertIn("you can redirect me at any time", normalized_example)

    def test_manifest_reference_documents_current_behavior_contract(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = normalize(
            (root / "docs/manifest-reference.md").read_text(encoding="utf-8")
        ).lower()

        for clause in (
            "`protocol_version`: exact protocol version `1.1.0`",
            "`conformance.version` is integer `2`",
            "silent orchestration",
            "vocabulary readiness",
            "connected perspectives",
            "productive effort",
            "graduated support",
            "agent-led route",
            "silent self-review",
            "autonomous current-information research",
            "protocol `1.1.0`",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, text)

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

    def test_readme_orders_onboarding_and_scopes_channel_availability(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "README.md").read_text(encoding="utf-8")
        quick_start = text.split("## Quick start", 1)[1].split(
            "## Supported hosts and project adapters",
            1,
        )[0]
        normalized_quick_start = " ".join(quick_start.split())

        ordered_markers = (
            VERSIONED_INSTALLER_URLS[0],
            VERSIONED_INSTALLER_URLS[1],
            "pipx install socratic-learn",
            "\nsocratic\n",
            'socratic "I want to learn linear algebra"',
            "socratic --agent pi",
            "socratic --here",
        )
        previous = -1
        for marker in ordered_markers:
            position = quick_start.find(marker)
            with self.subTest(marker=marker):
                self.assertGreater(position, previous)
            previous = position
        self.assertIn(NATIVE_RELEASE_CAVEAT, normalized_quick_start)
        self.assertIn(PYPI_RELEASE_CAVEAT, normalized_quick_start)
        self.assertLess(
            normalized_quick_start.index(NATIVE_RELEASE_CAVEAT),
            normalized_quick_start.index(VERSIONED_INSTALLER_URLS[0]),
        )
        self.assertLess(
            normalized_quick_start.index(PYPI_RELEASE_CAVEAT),
            normalized_quick_start.index("pipx install socratic-learn"),
        )
        self.assertNotIn("raw.githubusercontent.com", quick_start)
        self.assertNotRegex(quick_start, r"(?is)\birm\b[^\n|]*\|\s*iex\b")
        self.assertNotRegex(quick_start, r"(?is)\bcurl\b[^\n|]*\|\s*(?:ba)?sh\b")

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
        self.assertIn(NATIVE_RELEASE_CAVEAT.lower(), installation_normalized)
        self.assertIn(PYPI_RELEASE_CAVEAT.lower(), installation_normalized)
        self.assertNotIn("raw.githubusercontent.com", installation)
        self.assertNotRegex(installation, r"(?is)\birm\b[^\n|]*\|\s*iex\b")
        self.assertNotRegex(
            installation,
            r"(?is)\bcurl\b[^\n|]*\|\s*(?:ba)?sh\b",
        )

    def test_validator_rejects_narrow_readme_positioning(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        readme = root / "README.md"
        text = readme.read_text(encoding="utf-8")
        text = text.replace(
            README_TAGLINE,
            "A portable Socratic learning protocol for mathematics and AI.",
        ).replace("any subject or skill", "mathematics and AI")
        readme.write_text(text, encoding="utf-8")

        self.assertIn(
            "Narrow product positioning in README.md",
            validate(root),
        )

    def test_validator_requires_any_subject_in_readme_opening(self) -> None:
        replacements = (
            (
                "A portable, evidence-aware Socratic protocol for learning any subject.",
                "A portable Socratic protocol.",
            ),
            ("learn any subject", "study selected topics"),
        )
        for original, replacement in replacements:
            with self.subTest(original=original):
                temp, root = self.make_root()
                self.addCleanup(temp.cleanup)
                readme = root / "README.md"
                opening, marker, remainder = readme.read_text(
                    encoding="utf-8"
                ).partition("## Why I built this")
                self.assertIn(original, opening)
                readme.write_text(
                    opening.replace(original, replacement) + marker + remainder,
                    encoding="utf-8",
                )
                self.assertIn(
                    "Narrow product positioning in README.md",
                    validate(root),
                )

    def test_validator_requires_any_subject_in_first_prose_paragraph(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        readme = root / "README.md"
        text = readme.read_text(encoding="utf-8")
        tagline = f"**{README_TAGLINE}**"
        before_tagline, separator, after_tagline = text.partition(tagline)
        self.assertEqual(separator, tagline)
        first_paragraph, paragraph_break, later_text = after_tagline.lstrip(
            "\r\n"
        ).partition("\n\n")
        self.assertEqual(paragraph_break, "\n\n")
        self.assertIn(README_OPENING_PROMISE, first_paragraph)
        first_paragraph = first_paragraph.replace(
            README_OPENING_PROMISE,
            "study selected topics",
        )
        later_text = (
            "Compatible agents can still help people learn any subject.\n\n"
            + later_text
        )
        readme.write_text(
            before_tagline
            + tagline
            + "\n\n"
            + first_paragraph
            + paragraph_break
            + later_text,
            encoding="utf-8",
        )

        self.assertIn(
            "Narrow product positioning in README.md",
            validate(root),
        )

    def test_validator_ignores_hidden_opening_contract_in_html_comment(
        self,
    ) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        readme = root / "README.md"
        text = readme.read_text(encoding="utf-8")
        tagline = f"**{README_TAGLINE}**"
        hidden_contract = (
            "<!--\n"
            f"{tagline}\n\n"
            "Hidden agents help people learn any subject.\n"
            "-->\n\n"
        )
        text = text.replace(
            README_OPENING_PROMISE,
            "study selected topics",
            1,
        ).replace(
            tagline,
            hidden_contract + "**A portable Socratic learning protocol.**",
            1,
        )
        readme.write_text(text, encoding="utf-8")

        self.assertIn(
            "Narrow product positioning in README.md",
            validate(root),
        )

    def test_validator_rejects_non_prose_first_opening_block(self) -> None:
        first_blocks = (
            ("blockquote", "> learn any subject"),
            ("fenced_code", "```text\nlearn any subject\n```"),
            ("heading", "### Learn any subject"),
            ("html_block", "<div>learn any subject</div>"),
            ("indented_code", "    learn any subject"),
            ("ordered_list", "1. learn any subject"),
            (
                "table",
                "Promise | Status\n--- | ---\nlearn any subject | present",
            ),
            ("thematic_break", "---"),
            ("unordered_list", "- learn any subject"),
        )
        for name, first_block in first_blocks:
            with self.subTest(block=name):
                temp, root = self.make_root()
                self.addCleanup(temp.cleanup)
                readme = root / "README.md"
                text = readme.read_text(encoding="utf-8")
                opening, heading, remainder = text.partition("## Why I built this")
                tagline = f"**{README_TAGLINE}**"
                before_tagline, separator, after_tagline = opening.partition(
                    tagline
                )
                self.assertEqual(separator, tagline)
                first_paragraph, paragraph_break, later_opening = (
                    after_tagline.lstrip("\r\n").partition("\n\n")
                )
                self.assertEqual(paragraph_break, "\n\n")
                first_paragraph = first_paragraph.replace(
                    README_OPENING_PROMISE,
                    "study selected topics",
                )
                mutated_opening = (
                    before_tagline
                    + tagline
                    + "\n\n"
                    + first_block
                    + "\n\n"
                    + first_paragraph
                    + "\n\nCompatible agents can still help people "
                    "learn any subject.\n\n"
                    + later_opening
                )
                readme.write_text(
                    mutated_opening + heading + remainder,
                    encoding="utf-8",
                )

                self.assertIn(
                    "Narrow product positioning in README.md",
                    validate(root),
                )

    def test_validator_rejects_indented_markdown_opening_blocks(self) -> None:
        blocks = (
            ("heading", "### Learn any subject"),
            ("blockquote", "> learn any subject"),
            ("unordered_list", "- learn any subject"),
            ("ordered_list", "1. learn any subject"),
            ("html_block", "<section>learn any subject</section>"),
        )
        for spaces in (1, 2, 3):
            for name, block in blocks:
                with self.subTest(spaces=spaces, block=name):
                    temp, root = self.make_root()
                    self.addCleanup(temp.cleanup)
                    readme = root / "README.md"
                    text = readme.read_text(encoding="utf-8")
                    tagline = f"**{README_TAGLINE}**"
                    opening, heading, remainder = text.partition(
                        "## Why I built this"
                    )
                    before, separator, after = opening.partition(tagline)
                    self.assertEqual(separator, tagline)
                    first_paragraph, paragraph_break, later = (
                        after.lstrip("\r\n").partition("\n\n")
                    )
                    self.assertEqual(paragraph_break, "\n\n")
                    first_paragraph = first_paragraph.replace(
                        README_OPENING_PROMISE,
                        "study selected topics",
                    )
                    indented_block = " " * spaces + block
                    readme.write_text(
                        before
                        + tagline
                        + "\n\n"
                        + indented_block
                        + "\n\n"
                        + first_paragraph
                        + "\n\nCompatible agents can still help people "
                        "learn any subject.\n\n"
                        + later
                        + heading
                        + remainder,
                        encoding="utf-8",
                    )

                    self.assertIn(
                        "Narrow product positioning in README.md",
                        validate(root),
                    )

    def test_validator_rejects_empty_atx_and_complete_html_blocks(self) -> None:
        blocks = (
            ("empty_atx", "###"),
            ("span_open", "<span>"),
            ("span_close", "</span>"),
            ("custom_open", '<x-note role="note">'),
            ("custom_close", "</x-note>"),
        )
        for spaces in (0, 1, 2, 3):
            for name, block in blocks:
                with self.subTest(spaces=spaces, block=name):
                    temp, root = self.make_root()
                    self.addCleanup(temp.cleanup)
                    readme = root / "README.md"
                    text = readme.read_text(encoding="utf-8")
                    tagline = f"**{README_TAGLINE}**"
                    opening, heading, remainder = text.partition(
                        "## Why I built this"
                    )
                    before, separator, after = opening.partition(tagline)
                    self.assertEqual(separator, tagline)
                    first_paragraph, paragraph_break, later = (
                        after.lstrip("\r\n").partition("\n\n")
                    )
                    self.assertEqual(paragraph_break, "\n\n")
                    first_paragraph = first_paragraph.replace(
                        README_OPENING_PROMISE,
                        "study selected topics",
                    )
                    first_block = (
                        " " * spaces + block + "\nlearn any subject"
                    )
                    readme.write_text(
                        before
                        + tagline
                        + "\n\n"
                        + first_block
                        + "\n\n"
                        + first_paragraph
                        + paragraph_break
                        + later
                        + heading
                        + remainder,
                        encoding="utf-8",
                    )

                    self.assertIn(
                        "Narrow product positioning in README.md",
                        validate(root),
                    )

    def test_validator_accepts_inline_html_or_autolink_opening_prose(self) -> None:
        paragraphs = (
            "<https://example.com> helps people learn any subject.",
            "<span>Visible</span> agents help people learn any subject.",
        )
        for paragraph in paragraphs:
            with self.subTest(paragraph=paragraph):
                temp, root = self.make_root()
                self.addCleanup(temp.cleanup)
                readme = root / "README.md"
                text = readme.read_text(encoding="utf-8")
                tagline = f"**{README_TAGLINE}**"
                before, separator, after = text.partition(tagline)
                self.assertEqual(separator, tagline)
                _, paragraph_break, later = after.lstrip(
                    "\r\n"
                ).partition("\n\n")
                self.assertEqual(paragraph_break, "\n\n")
                readme.write_text(
                    before
                    + tagline
                    + "\n\n"
                    + paragraph
                    + paragraph_break
                    + later,
                    encoding="utf-8",
                )

                self.assertNotIn(
                    "Narrow product positioning in README.md",
                    validate(root),
                )

    def test_validator_rejects_unfriendly_readme_dash_punctuation(self) -> None:
        for dash in README_UNFRIENDLY_DASHES:
            with self.subTest(dash=dash):
                temp, root = self.make_root()
                self.addCleanup(temp.cleanup)
                readme = root / "README.md"
                readme.write_text(
                    readme.read_text(encoding="utf-8")
                    + f"\nA friendly sentence{dash}with an unfriendly dash.\n",
                    encoding="utf-8",
                )
                self.assertIn(
                    "README.md uses unfriendly dash punctuation",
                    validate(root),
                )

    def test_validator_rejects_missing_portfolio_narrative(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        readme = root / "README.md"
        text = readme.read_text(encoding="utf-8")
        text = text.replace(
            "I built Socratic Learn out of a recurring need in my work as an AI researcher",
            "Socratic Learn is a learning tool",
        )
        readme.write_text(text, encoding="utf-8")

        self.assertIn(
            "README.md is missing portfolio narrative",
            validate(root),
        )

    def test_validator_rejects_missing_research_or_baseline_evidence(self) -> None:
        replacements = (
            ("Mahoney et al. (2023)", "A prior study"),
            ("Lee et al. (2025)", "A recent study"),
            ("no pedagogy score was assigned", "the sessions were successful"),
        )
        for original, replacement in replacements:
            with self.subTest(original=original):
                temp, root = self.make_root()
                self.addCleanup(temp.cleanup)
                readme = root / "README.md"
                readme.write_text(
                    readme.read_text(encoding="utf-8").replace(original, replacement),
                    encoding="utf-8",
                )
                self.assertIn(
                    "README.md is missing portfolio narrative",
                    validate(root),
                )

    def test_validator_rejects_each_missing_portfolio_requirement(self) -> None:
        for requirement in README_PORTFOLIO_REQUIREMENTS:
            with self.subTest(requirement=requirement):
                temp, root = self.make_root()
                self.addCleanup(temp.cleanup)
                readme = root / "README.md"
                text = readme.read_text(encoding="utf-8")
                while requirement_pattern(requirement).search(text):
                    text = replace_requirement_once(
                        text,
                        requirement,
                        "removed portfolio requirement",
                    )
                readme.write_text(
                    text,
                    encoding="utf-8",
                )
                self.assertIn(
                    "README.md is missing portfolio narrative",
                    validate(root),
                )

    def test_portfolio_mutation_tolerates_wrapped_requirement(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        readme = root / "README.md"
        requirement = "three unchanged-protocol Antigravity sessions"
        text = readme.read_text(encoding="utf-8").replace(
            requirement,
            "three unchanged-protocol\nAntigravity sessions",
            1,
        )
        readme.write_text(text, encoding="utf-8")
        self.assertNotIn(
            "README.md is missing portfolio narrative",
            validate(root),
        )

        readme.write_text(
            replace_requirement_once(
                text,
                requirement,
                "removed portfolio requirement",
            ),
            encoding="utf-8",
        )
        self.assertIn(
            "README.md is missing portfolio narrative",
            validate(root),
        )

    def test_validator_rejects_unsupported_effectiveness_claim(self) -> None:
        claims = (
            "Socratic Learn is proven to improve learning.",
            "Socratic Learn is scientifically\nvalidated to improve learning.",
            "Research\nproves that Socratic Learn improves learning.",
            "Studies validate\nSocratic Learn.",
            "Literature validates that\nSocratic Learn.",
            "Socratic Learn improves learning.",
            "Socratic\nLearn improves\nlearning.",
            "Evidence shows that Socratic Learn improves learning.",
            "Research\ndemonstrates that Socratic Learn improves learning.",
        )
        for claim in claims:
            with self.subTest(claim=claim):
                temp, root = self.make_root()
                self.addCleanup(temp.cleanup)
                readme = root / "README.md"
                readme.write_text(
                    readme.read_text(encoding="utf-8") + f"\n{claim}\n",
                    encoding="utf-8",
                )

                self.assertIn(
                    "README.md contains an unsupported effectiveness claim",
                    validate(root),
                )

    def test_validator_allows_negated_effectiveness_wording(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        readme = root / "README.md"
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\nSocratic Learn is not proven to improve learning.\n"
            + "Socratic Learn does not improve learning.\n"
            + "Research does not prove that Socratic Learn improves learning.\n"
            + "Evidence does not show that Socratic Learn improves learning.\n"
            + "No research proves that Socratic Learn improves learning.\n"
            + "No\nevidence demonstrates that Socratic Learn improves learning.\n",
            encoding="utf-8",
        )

        self.assertNotIn(
            "README.md contains an unsupported effectiveness claim",
            validate(root),
        )

    def test_validator_allows_approved_readme_effectiveness_caveats(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)

        self.assertNotIn(
            "README.md contains an unsupported effectiveness claim",
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

    def test_validator_rejects_missing_channel_availability_caveats(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        for relative in ("README.md", "docs/universal-installation.md"):
            with self.subTest(relative=relative):
                path = root / relative
                original = path.read_text(encoding="utf-8")
                unsafe = re.sub(
                    r"Native installation is\s+available only after GitHub "
                    r"Release\s+v0[.]1[.]0 is published[.]",
                    "Install the native release.",
                    original,
                )
                unsafe = re.sub(
                    r"The pipx command is available only after\s+"
                    r"socratic-learn 0[.]1[.]0 is published on\s+PyPI[.]",
                    "Install with pipx.",
                    unsafe,
                )
                path.write_text(unsafe, encoding="utf-8")
                self.assertIn(
                    f"{relative} must condition native and PyPI instructions "
                    "on publication",
                    validate(root),
                )
                path.write_text(original, encoding="utf-8")

    def test_validator_rejects_mutable_or_piped_installer_commands(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        unsafe_examples = (
            (
                VERSIONED_INSTALLER_URLS[0],
                "https://raw.githubusercontent.com/marcos-guilherme/"
                "socratic-learn/main/scripts/install.ps1",
            ),
            (
                VERSIONED_INSTALLER_URLS[0],
                "https://github.com/marcos-guilherme/socratic-learn/"
                "raw/main/scripts/install.ps1",
            ),
            (
                VERSIONED_INSTALLER_URLS[1],
                "https://github.com/marcos-guilherme/socratic-learn/"
                "blob/main/scripts/install.sh",
            ),
            (
                VERSIONED_INSTALLER_URLS[0],
                "https://github.com/marcos-guilherme/socratic-learn/"
                "releases/latest/download/install.ps1",
            ),
            ("& $installer", "IWR $url | Invoke-Expression"),
            ("sh \"$installer\"", "wget -qO- $url | bash"),
        )
        for relative in ("README.md", "docs/universal-installation.md"):
            path = root / relative
            original = path.read_text(encoding="utf-8")
            for expected, unsafe in unsafe_examples:
                with self.subTest(relative=relative, unsafe=unsafe):
                    path.write_text(
                        original.replace(expected, unsafe, 1),
                        encoding="utf-8",
                    )
                    self.assertIn(
                        f"{relative} contains unsafe or mutable "
                        "installer instructions",
                        validate(root),
                    )
            path.write_text(original, encoding="utf-8")

    def test_unsafe_installer_regexes_cover_remote_execution_variants(self) -> None:
        self.assertTrue(
            all(
                isinstance(pattern, re.Pattern)
                for pattern in UNSAFE_INSTALLER_PATTERNS
            )
        )
        unsafe_examples = (
            "https://raw.githubusercontent.com/org/repo/main/scripts/install.sh",
            "https://github.com/org/repo/raw/main/scripts/install.ps1",
            "https://github.com/org/repo/blob/main/scripts/install.sh",
            "https://github.com/org/repo/releases/latest/download/install.ps1",
            "IrM   https://example.invalid/install.ps1   |   IEX",
            "iWr -UseBasicParsing $url\t|\tInvoke-Expression",
            "Invoke-WebRequest $url -UseBasicParsing\n | iex",
            "curl -fLsS https://example.invalid/install.sh | bash",
            "wget -qO- https://example.invalid/install.sh\n  |  sh -s",
        )
        for command in unsafe_examples:
            with self.subTest(command=command):
                self.assertTrue(
                    any(pattern.search(command) for pattern in UNSAFE_INSTALLER_PATTERNS)
                )

        safe_examples = (
            "Invoke-WebRequest $url -OutFile $installer",
            "curl -fL $url -o \"$installer\"",
            "wget $url -O \"$installer\"",
            "& $installer",
            "sh \"$installer\"",
        )
        for command in safe_examples:
            with self.subTest(command=command):
                self.assertFalse(
                    any(pattern.search(command) for pattern in UNSAFE_INSTALLER_PATTERNS)
                )

    def test_validator_requires_each_exact_installer_url_on_each_surface(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        for relative in ("README.md", "docs/universal-installation.md"):
            path = root / relative
            original = path.read_text(encoding="utf-8")
            for url in VERSIONED_INSTALLER_URLS:
                with self.subTest(relative=relative, url=url):
                    path.write_text(
                        original.replace(url, "https://example.invalid/installer", 1),
                        encoding="utf-8",
                    )
                    self.assertIn(
                        f"{relative} must use exact v0.1.0 PowerShell and "
                        "POSIX installer URLs",
                        validate(root),
                    )
            path.write_text(original, encoding="utf-8")

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

    def test_canonical_tutor_keeps_orchestration_internal(self) -> None:
        root = Path(__file__).resolve().parents[1]
        protocol = normalize(
            (root / "core/session-protocol.md").read_text(encoding="utf-8")
        ).lower()
        entry = normalize((root / "AGENTS.md").read_text(encoding="utf-8")).lower()
        for clause in (
            "keep protocol orchestration internal",
            "do not announce stage names",
            "diagnostic budgets",
            "question counters",
            "successful file writes",
            "unless the learner explicitly asks",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, protocol)
        self.assertIn("hide orchestration by default", entry)
        self.assertIn("persist approved context silently", entry)

    def test_canonical_tutor_requires_vocabulary_readiness_and_concept_ramp(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[1]
        pedagogy = normalize(
            (root / "core/pedagogy.md").read_text(encoding="utf-8")
        ).lower()
        for clause in (
            "vocabulary readiness",
            "the learner used it correctly",
            "demonstrated the underlying idea",
            "introduced it in plain language",
            "hidden prerequisites",
            "experience or intuitive problem",
            "concrete example",
            "conventional name",
            "formal notation or definition",
            "learner application",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, pedagogy)

    def test_canonical_tutor_connects_perspectives_and_productive_effort(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[1]
        pedagogy = normalize(
            (root / "core/pedagogy.md").read_text(encoding="utf-8")
        ).lower()
        for clause in (
            "one primary explanation",
            "up to two additional perspectives",
            "explicitly connect",
            "learner attempt before",
            "paper and pen",
            "do not include the solution",
            "small cue",
            "alternative representation or simpler case",
            "direct explanation",
            "new application",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, pedagogy)

    def test_assessment_starts_from_safe_evidence_not_topic_interest(self) -> None:
        root = Path(__file__).resolve().parents[1]
        assessment = normalize(
            (root / "core/assessment.md").read_text(encoding="utf-8")
        ).lower()
        for clause in (
            "motivation, topic interest, desired depth, and self-report are context",
            "not prerequisite evidence",
            "safest relevant foundation",
            "one meaningful dependency edge",
            "vocabulary-safe",
            "keep the diagnostic budget internal",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, assessment)
        self.assertNotIn("make a meaningful jump", assessment)

    def test_protocol_contrasts_premature_and_natural_opening(self) -> None:
        root = Path(__file__).resolve().parents[1]
        protocol = (root / "core/session-protocol.md").read_text(encoding="utf-8")
        bad = "Bad shape: turn broad motivation directly into a technical formula"
        good = 'Learner: "I want to study transformers."'
        response = (
            'Tutor: "What would you like to be able to do: explain the general '
            'idea, follow a small worked example, or build a simple version?"'
        )
        self.assertIn(bad, protocol)
        self.assertIn(good, protocol)
        self.assertIn(response, protocol)
        self.assertLess(protocol.index(bad), protocol.index(good))

    def test_canonical_tutor_owns_agent_led_route(self) -> None:
        root = Path(__file__).resolve().parents[1]
        protocol = normalize(
            (root / "core/session-protocol.md").read_text(encoding="utf-8")
        ).lower()
        entry = normalize((root / "AGENTS.md").read_text(encoding="utf-8")).lower()
        for clause in (
            "the tutor owns technical route selection",
            "do not ask the learner to validate a technical sequence",
            "brief preview in ordinary language",
            "begin teaching without formal approval",
            "the learner may redirect at any time",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, protocol)
        self.assertIn("the tutor owns technical route selection", entry)
        self.assertIn("begin teaching without formal approval", entry)

    def test_canonical_learner_owns_personal_learning_choices(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sources = {
            "pedagogy": normalize(
                (root / "core/pedagogy.md").read_text(encoding="utf-8")
            ).lower(),
            "session protocol": normalize(
                (root / "core/session-protocol.md").read_text(encoding="utf-8")
            ).lower(),
        }
        for source, text in sources.items():
            for clause in (
                "objective",
                "pace",
                "depth",
                "available time",
                "preferred representation",
                "redirection",
                "personal trade-offs",
                "pause",
                "skip",
                "revisit",
            ):
                with self.subTest(source=source, clause=clause):
                    self.assertIn(clause, text)

    def test_canonical_persistence_separates_personal_context_from_evidence(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[1]
        sources = {
            "agent entry": normalize(
                (root / "AGENTS.md").read_text(encoding="utf-8")
            ).lower(),
            "session protocol": normalize(
                (root / "core/session-protocol.md").read_text(encoding="utf-8")
            ).lower(),
        }
        for source, text in sources.items():
            for clause in (
                "objectives, preferences, and personal facts",
                "inferred personal context",
                "learner states or confirms",
                "demonstrated knowledge",
                "observed evidence",
                "task, conditions, result, and support",
                "without a new approval gate",
                "do not infer mastery or preference",
            ):
                with self.subTest(source=source, clause=clause):
                    self.assertIn(clause, text)
            self.assertNotIn(
                "never save inferred knowledge or outcomes before learner approval",
                text,
            )
            self.assertNotIn(
                "do not save inferred knowledge, preferences, or technical outcomes "
                "before approval",
                text,
            )

    def test_canonical_tutor_runs_silent_self_review(self) -> None:
        root = Path(__file__).resolve().parents[1]
        pedagogy = normalize(
            (root / "core/pedagogy.md").read_text(encoding="utf-8")
        ).lower()
        for clause in (
            "silent self-review",
            "alignment with the learner-owned objective",
            "prerequisite evidence",
            "vocabulary readiness and cognitive load",
            "the smallest useful next step",
            "whether a perspective contributes distinct value",
            "whether factual currency or uncertainty requires research",
            "whether the response asks the learner to make a decision they lack "
            "the basis to evaluate",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, pedagogy)

    def test_evidence_policy_requires_autonomous_private_research(self) -> None:
        root = Path(__file__).resolve().parents[1]
        evidence = normalize(
            (root / "core/evidence-policy.md").read_text(encoding="utf-8")
        ).lower()
        for clause in (
            "search autonomously",
            "consequential current, volatile, disputed, or uncertain claims",
            "primary sources",
            "date or version context",
            "external search queries",
            "exclude private learner data",
            "learner-profile content",
            "session records",
            "identifying context",
            "continues with stable material",
            "time-sensitive details unverified",
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, evidence)

    def test_canonical_route_removes_technical_approval_gate(self) -> None:
        root = Path(__file__).resolve().parents[1]
        sources = {
            "agent entry": (root / "AGENTS.md").read_text(encoding="utf-8"),
            "pedagogy": (root / "core/pedagogy.md").read_text(encoding="utf-8"),
            "session protocol": (
                root / "core/session-protocol.md"
            ).read_text(encoding="utf-8"),
        }
        for source, text in sources.items():
            normalized = normalize(text).lower()
            for clause in (
                "present and approve a dependency path",
                "do not begin teaching until the learner approves",
                "obtain learner approval before teaching",
                "obtain approval again",
                "confirm the objective and proposed route",
            ):
                with self.subTest(source=source, clause=clause):
                    self.assertNotIn(clause, normalized)

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
            "macos-15-intel",
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
        self.assertNotIn("macos-13", release)

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

    def test_release_workflow_rejects_retired_macos_intel_runner(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        release.write_text(
            release.read_text(encoding="utf-8").replace(
                "macos-15-intel",
                "macos-13",
                1,
            ),
            encoding="utf-8",
        )

        errors = validate(root)

        self.assertIn(
            "Native macOS release matrix must use macos-15-intel "
            "with an empty extension",
            errors,
        )

    def test_release_workflow_rejects_arm_macos_runner_with_comment_decoy(
        self,
    ) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        release.write_text(
            release.read_text(encoding="utf-8").replace(
                "          - os: macos-15-intel\n"
                "            platform: macos\n",
                "          - os: macos-15  # macos-15-intel\n"
                "            platform: macos\n",
                1,
            ),
            encoding="utf-8",
        )

        errors = validate(root)

        self.assertIn(
            "Native macOS release matrix must use macos-15-intel "
            "with an empty extension",
            errors,
        )

    def test_release_workflow_rejects_arm_macos_runner_with_matrix_decoy(
        self,
    ) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        text = release.read_text(encoding="utf-8").replace(
            "          - os: macos-15-intel\n"
            "            platform: macos\n",
            "          - os: macos-15\n"
            "            platform: macos\n",
            1,
        )
        text = text.replace(
            "          - os: windows-latest\n",
            "          - os: macos-15-intel\n"
            "            platform: decoy\n"
            '            extension: ""\n'
            "          - os: windows-latest\n",
            1,
        )
        release.write_text(text, encoding="utf-8")

        errors = validate(root)

        self.assertIn(
            "Native macOS release matrix must use macos-15-intel "
            "with an empty extension",
            errors,
        )

    def test_release_workflow_rejects_arm64_rename_with_comment_decoy(
        self,
    ) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        expected = "f\"socratic-{os.environ['RELEASE_PLATFORM']}-x86_64\""
        text = release.read_text(encoding="utf-8").replace(
            expected,
            "f\"socratic-{os.environ['RELEASE_PLATFORM']}-arm64\"\n"
            f"              # {expected}",
            1,
        )
        release.write_text(text, encoding="utf-8")

        errors = validate(root)

        self.assertIn(
            "Native rename and upload steps must produce x86_64 artifacts",
            errors,
        )

    def test_release_workflow_rejects_arm64_upload_path_with_comment_decoy(
        self,
    ) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        expected = (
            "path: native-artifacts/socratic-${{ matrix.platform }}"
            "-x86_64${{ matrix.extension }}"
        )
        text = release.read_text(encoding="utf-8").replace(
            expected,
            "path: native-artifacts/socratic-${{ matrix.platform }}"
            "-arm64${{ matrix.extension }}\n"
            f"          # {expected}",
            1,
        )
        release.write_text(text, encoding="utf-8")

        errors = validate(root)

        self.assertIn(
            "Native rename and upload steps must produce x86_64 artifacts",
            errors,
        )

    def test_release_version_gate_requires_local_importability(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        release.write_text(
            release.read_text(encoding="utf-8").replace(
                "          sys.path.insert(0, os.getcwd())\n",
                "",
                1,
            ),
            encoding="utf-8",
        )

        errors = validate(root)

        self.assertIn(
            "Release version gate must add the checkout to sys.path before import",
            errors,
        )

    def test_release_version_gate_rejects_commented_path_setup(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        release.write_text(
            release.read_text(encoding="utf-8").replace(
                "          sys.path.insert(0, os.getcwd())\n",
                "          # sys.path.insert(0, os.getcwd())\n",
                1,
            ),
            encoding="utf-8",
        )

        errors = validate(root)

        self.assertIn(
            "Release version gate must add the checkout to sys.path before import",
            errors,
        )

    def test_release_version_gate_rejects_nested_dead_path_setup(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        release.write_text(
            release.read_text(encoding="utf-8").replace(
                "          sys.path.insert(0, os.getcwd())\n",
                "          if False:\n"
                "              sys.path.insert(0, os.getcwd())\n",
                1,
            ),
            encoding="utf-8",
        )

        errors = validate(root)

        self.assertIn(
            "Release version gate must add the checkout to sys.path before import",
            errors,
        )

    def test_release_version_gate_rejects_import_before_setup_and_duplicate(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        release.write_text(
            release.read_text(encoding="utf-8").replace(
                "          sys.path.insert(0, os.getcwd())\n",
                "          from socratic_learn import __version__\n"
                "          sys.path.insert(0, os.getcwd())\n",
                1,
            ),
            encoding="utf-8",
        )

        errors = validate(root)

        self.assertIn(
            "Release version gate must add the checkout to sys.path before import",
            errors,
        )

    def test_release_version_gate_rejects_aliased_os_import(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        release.write_text(
            release.read_text(encoding="utf-8").replace(
                "          import os\n",
                "          import os as operating_system\n",
                1,
            ),
            encoding="utf-8",
        )

        self.assertIn(
            "Release version gate must add the checkout to sys.path before import",
            validate(root),
        )

    def test_release_version_gate_rejects_aliased_sys_import(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        release.write_text(
            release.read_text(encoding="utf-8").replace(
                "          import sys\n",
                "          import sys as system\n",
                1,
            ),
            encoding="utf-8",
        )

        self.assertIn(
            "Release version gate must add the checkout to sys.path before import",
            validate(root),
        )

    def test_release_version_gate_rejects_aliased_version_import(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        release.write_text(
            release.read_text(encoding="utf-8").replace(
                "          from socratic_learn import __version__\n",
                "          from socratic_learn import __version__ as version\n",
                1,
            ),
            encoding="utf-8",
        )

        self.assertIn(
            "Release version gate must add the checkout to sys.path before import",
            validate(root),
        )

    def test_release_version_gate_rejects_setup_in_separate_step(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        text = release.read_text(encoding="utf-8")
        setup = (
            "      - name: Ineffective separate path setup\n"
            "        shell: python\n"
            "        run: |\n"
            "          import os\n"
            "          import sys\n"
            "          sys.path.insert(0, os.getcwd())\n"
        )
        text = text.replace(
            "          sys.path.insert(0, os.getcwd())\n",
            "",
            1,
        ).replace(
            "      - name: Require an exact version tag\n",
            setup + "      - name: Require an exact version tag\n",
            1,
        )
        release.write_text(text, encoding="utf-8")

        errors = validate(root)

        self.assertIn(
            "Release version gate must add the checkout to sys.path before import",
            errors,
        )

    def test_release_manifest_step_establishes_local_importability(self) -> None:
        release = (
            Path(__file__).resolve().parents[1] / ".github/workflows/release.yml"
        ).read_text(encoding="utf-8")
        manifest = release.split("  manifest:", 1)[1].split(
            "  publish-github:", 1
        )[0]

        self.assertIn("          import os\n", manifest)
        self.assertIn("          import sys\n", manifest)
        self.assertIn(
            "          sys.path.insert(0, os.getcwd())\n",
            manifest,
        )
        self.assertLess(
            manifest.index("          sys.path.insert(0, os.getcwd())\n"),
            manifest.index("          from socratic_learn import __version__\n"),
        )

    def test_release_manifest_import_setup_mutations_are_rejected(self) -> None:
        mutations = {
            "missing": "",
            "commented": "# sys.path.insert(0, os.getcwd())",
            "nested dead code": (
                "if False:\n"
                "              sys.path.insert(0, os.getcwd())"
            ),
            "after local import": (
                "from socratic_learn import __version__\n"
                "          sys.path.insert(0, os.getcwd())"
            ),
        }
        for label, replacement in mutations.items():
            with self.subTest(label=label):
                temp, root = self.make_root()
                self.addCleanup(temp.cleanup)
                release = root / ".github/workflows/release.yml"
                before_manifest, manifest = release.read_text(
                    encoding="utf-8"
                ).split("  manifest:", 1)
                manifest = manifest.replace(
                    "          sys.path.insert(0, os.getcwd())",
                    f"          {replacement}" if replacement else "",
                    1,
                )
                release.write_text(
                    before_manifest + "  manifest:" + manifest,
                    encoding="utf-8",
                )

                self.assertIn(
                    "Every release shell: python step importing socratic_learn "
                    "must add the checkout to sys.path before import",
                    validate(root),
                )

    def test_release_manifest_import_setup_requires_exact_dependency_names(
        self,
    ) -> None:
        for original, replacement in (
            ("          import os\n", "          import os as operating_system\n"),
            ("          import sys\n", "          import sys as system\n"),
        ):
            with self.subTest(original=original):
                temp, root = self.make_root()
                self.addCleanup(temp.cleanup)
                release = root / ".github/workflows/release.yml"
                before_manifest, manifest = release.read_text(
                    encoding="utf-8"
                ).split("  manifest:", 1)
                manifest = manifest.replace(original, replacement, 1)
                release.write_text(
                    before_manifest + "  manifest:" + manifest,
                    encoding="utf-8",
                )

                self.assertIn(
                    "Every release shell: python step importing socratic_learn "
                    "must add the checkout to sys.path before import",
                    validate(root),
                )

    def test_release_manifest_rejects_setup_in_separate_step(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        before_manifest, manifest = release.read_text(encoding="utf-8").split(
            "  manifest:", 1
        )
        manifest = manifest.replace(
            "          sys.path.insert(0, os.getcwd())\n",
            "",
            1,
        ).replace(
            "      - name: Compute and validate release metadata\n",
            "      - name: Ineffective separate manifest path setup\n"
            "        shell: python\n"
            "        run: |\n"
            "          import os\n"
            "          import sys\n"
            "          sys.path.insert(0, os.getcwd())\n"
            "      - name: Compute and validate release metadata\n",
            1,
        )
        release.write_text(
            before_manifest + "  manifest:" + manifest,
            encoding="utf-8",
        )

        self.assertIn(
            "Every release shell: python step importing socratic_learn "
            "must add the checkout to sys.path before import",
            validate(root),
        )

    def test_release_local_import_validation_supports_literal_chomping(
        self,
    ) -> None:
        for scalar in ("|-", "|+"):
            with self.subTest(scalar=scalar):
                temp, root = self.make_root()
                self.addCleanup(temp.cleanup)
                release = root / ".github/workflows/release.yml"
                before_manifest, manifest = release.read_text(
                    encoding="utf-8"
                ).split("  manifest:", 1)
                manifest = manifest.replace(
                    "        run: |\n",
                    f"        run: {scalar}\n",
                    1,
                ).replace(
                    "          sys.path.insert(0, os.getcwd())\n",
                    "",
                    1,
                )
                release.write_text(
                    before_manifest + "  manifest:" + manifest,
                    encoding="utf-8",
                )

                self.assertIn(
                    "Every release shell: python step importing socratic_learn "
                    "must add the checkout to sys.path before import",
                    validate(root),
                )

    def test_release_python_steps_reject_folded_run_blocks(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        before_manifest, manifest = release.read_text(encoding="utf-8").split(
            "  manifest:", 1
        )
        manifest = manifest.replace(
            "        run: |\n",
            "        run: >-\n",
            1,
        )
        release.write_text(
            before_manifest + "  manifest:" + manifest,
            encoding="utf-8",
        )

        self.assertIn(
            "Release shell: python steps must use a literal run block",
            validate(root),
        )

    def test_release_local_import_validation_normalizes_python_shell_scalar(
        self,
    ) -> None:
        declarations = (
            'shell: "python"',
            "shell: 'python'",
            "shell: python # Python temp script",
            'shell: "python" # Python temp script',
        )
        for declaration in declarations:
            with self.subTest(declaration=declaration):
                temp, root = self.make_root()
                self.addCleanup(temp.cleanup)
                release = root / ".github/workflows/release.yml"
                before_manifest, manifest = release.read_text(
                    encoding="utf-8"
                ).split("  manifest:", 1)
                manifest = manifest.replace(
                    "        shell: python\n",
                    f"        {declaration}\n",
                    1,
                ).replace(
                    "          sys.path.insert(0, os.getcwd())\n",
                    "",
                    1,
                )
                release.write_text(
                    before_manifest + "  manifest:" + manifest,
                    encoding="utf-8",
                )

                self.assertIn(
                    "Every release shell: python step importing socratic_learn "
                    "must add the checkout to sys.path before import",
                    validate(root),
                )

    def test_release_local_import_validation_recognizes_python_placeholder(
        self,
    ) -> None:
        declarations = (
            "shell: python {0}",
            'shell: "python {0}"',
            "shell: 'python {0}' # Python temp script",
        )
        for declaration in declarations:
            with self.subTest(declaration=declaration):
                temp, root = self.make_root()
                self.addCleanup(temp.cleanup)
                release = root / ".github/workflows/release.yml"
                before_manifest, manifest = release.read_text(
                    encoding="utf-8"
                ).split("  manifest:", 1)
                manifest = manifest.replace(
                    "        shell: python\n",
                    f"        {declaration}\n",
                    1,
                ).replace(
                    "          sys.path.insert(0, os.getcwd())\n",
                    "",
                    1,
                )
                release.write_text(
                    before_manifest + "  manifest:" + manifest,
                    encoding="utf-8",
                )

                self.assertIn(
                    "Every release shell: python step importing socratic_learn "
                    "must add the checkout to sys.path before import",
                    validate(root),
                )

    def test_release_workflow_rejects_inherited_run_shell_defaults(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        release = root / ".github/workflows/release.yml"
        before_manifest, manifest = release.read_text(encoding="utf-8").split(
            "  manifest:", 1
        )
        manifest = manifest.replace(
            "        shell: python\n",
            "",
            1,
        ).replace(
            "\n    needs: native\n",
            "\n    defaults:\n"
            "      run:\n"
            "        shell: python\n"
            "    needs: native\n",
            1,
        )
        release.write_text(
            before_manifest + "  manifest:" + manifest,
            encoding="utf-8",
        )

        errors = validate(root)

        self.assertIn(
            "Release workflow must not use defaults.run.shell; "
            "Python steps must declare shell explicitly",
            errors,
        )
        self.assertNotIn(
            "Release shell: python steps must use a literal run block",
            errors,
        )

    def test_local_release_gates_isolate_package_output_from_canonical_dist(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[1]
        plan = (
            root
            / "docs/superpowers/plans/2026-11-06-one-command-learning-launcher.md"
        ).read_text(encoding="utf-8")
        commands = re.findall(r"(?m)^python -m build(?:[ \t].*)?$", plan)

        self.assertEqual(
            ["python -m build --outdir package-dist"] * 3,
            commands,
        )
        self.assertIn("/package-dist/", (root / ".gitignore").read_text("utf-8"))
        self.assertEqual(
            {"manifest.json", "socratic-learn.prompt.md"},
            {path.name for path in (root / "dist").iterdir()},
        )
        self.assertNotEqual("dist", "package-dist")

    def test_validator_rejects_bare_local_build_and_missing_package_ignore(
        self,
    ) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        plan = (
            root
            / "docs/superpowers/plans/2026-11-06-one-command-learning-launcher.md"
        )
        plan.write_text(
            plan.read_text(encoding="utf-8").replace(
                "python -m build --outdir package-dist",
                "python -m build",
                1,
            ),
            encoding="utf-8",
        )
        gitignore = root / ".gitignore"
        gitignore.write_text(
            gitignore.read_text(encoding="utf-8").replace("/package-dist/\n", ""),
            encoding="utf-8",
        )

        errors = validate(root)

        self.assertIn(
            "Active local release gates must use "
            "python -m build --outdir package-dist",
            errors,
        )
        self.assertIn(".gitignore must ignore /package-dist/", errors)

    def test_validator_rejects_package_artifacts_in_canonical_dist(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / "dist/socratic_learn-0.1.0-py3-none-any.whl").write_bytes(
            b"package"
        )

        self.assertIn(
            "Canonical dist/ must contain exactly manifest.json and "
            "socratic-learn.prompt.md; package builds use package-dist/",
            validate(root),
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

    def test_validator_requires_semantic_runs_ignore_rule(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        gitignore = root / ".gitignore"
        gitignore.write_text(
            gitignore.read_text(encoding="utf-8").replace(
                "/.semantic-runs/\n",
                "",
            ),
            encoding="utf-8",
        )

        self.assertIn(
            ".gitignore must ignore /.semantic-runs/",
            validate(root),
        )

    def test_validator_rejects_tracked_raw_semantic_evidence(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        raw = root / ".semantic-runs/raw.ndjson"
        raw.parent.mkdir(parents=True)
        raw.write_text('{"private": true}\n', encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(
            ["git", "add", "-f", ".semantic-runs/raw.ndjson"],
            cwd=root,
            check=True,
        )

        self.assertIn(
            "Tracked raw semantic evaluation files: .semantic-runs/raw.ndjson",
            validate(root),
        )

    def test_validator_rejects_runtime_home_under_semantic_runs(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / ".semantic-runs/suite/scenario/home/learning").mkdir(
            parents=True
        )

        self.assertIn(
            "Runtime home/cwd under .semantic-runs: suite/scenario/home",
            semantic_runtime_errors(root),
        )

    def test_validator_rejects_runtime_cwd_under_semantic_runs(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / ".semantic-runs/suite/scenario/learning/.socratic-learn").mkdir(
            parents=True
        )

        self.assertIn(
            "Runtime home/cwd under .semantic-runs: suite/scenario/learning",
            semantic_runtime_errors(root),
        )

    def test_validator_rejects_symlinked_semantic_runs_root(self) -> None:
        temp, root = self.make_root(nested_under_workspace=True)
        self.addCleanup(temp.cleanup)
        target = Path(temp.name) / "external-runtime-root"
        (target / "home/learning").mkdir(parents=True)
        self.require_symlink(
            root / ".semantic-runs",
            target,
            target_is_directory=True,
        )

        self.assertEqual(
            ["Unsafe symlink under .semantic-runs: ."],
            semantic_runtime_errors(root),
        )

    def test_validator_rejects_symlinked_semantic_run_directory(self) -> None:
        temp, root = self.make_root(nested_under_workspace=True)
        self.addCleanup(temp.cleanup)
        raw_root = root / ".semantic-runs"
        raw_root.mkdir()
        target = Path(temp.name) / "external-runtime"
        (target / "home/learning").mkdir(parents=True)
        self.require_symlink(
            raw_root / "suite",
            target,
            target_is_directory=True,
        )

        with patch("builtins.open", side_effect=AssertionError("raw content read")):
            errors = semantic_runtime_errors(root)

        self.assertEqual(
            ["Unsafe symlink under .semantic-runs: suite"],
            errors,
        )

    def test_raw_semantic_tree_is_not_runtime_placement(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        for relative in (
            ".semantic-runs/suite/scenario/raw/output.ndjson",
            ".semantic-runs/suite/scenario/raw/runtime-context.json",
            ".semantic-runs/suite/scenario/raw/learner-records/progress.md",
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("raw evidence\n", encoding="utf-8")

        self.assertEqual([], semantic_runtime_errors(root))

    def test_validator_rejects_unsafe_tracked_evaluation_assets(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        fixture = root / "evaluation/fixtures/antigravity/leak.json"
        fixture.parent.mkdir(parents=True)
        fixture.write_text(
            '{"Authorization": "Bearer provider-secret"}\n',
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(
            ["git", "add", "-f", "evaluation/fixtures/antigravity/leak.json"],
            cwd=root,
            check=True,
        )

        self.assertIn(
            "Unsafe tracked evaluation asset: "
            "evaluation/fixtures/antigravity/leak.json",
            validate(root),
        )

    def test_validator_rejects_guarded_tracked_asset_symlinks_without_reading(
        self,
    ) -> None:
        for label, target_relative in (
            ("external", "outside-provider-data.json"),
            ("ignored raw", ".semantic-runs/raw-provider-data.json"),
        ):
            with self.subTest(target=label):
                temp, root = self.make_root(
                    nested_under_workspace=label == "external"
                )
                self.addCleanup(temp.cleanup)
                target = (
                    Path(temp.name) / target_relative
                    if label == "external"
                    else root / target_relative
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    '{"Authorization": "Bearer provider-secret"}\n',
                    encoding="utf-8",
                )
                guarded = (
                    root / "evaluation/fixtures/antigravity/tracked-link.json"
                )
                guarded.parent.mkdir(parents=True)
                self.require_symlink(
                    guarded,
                    target,
                    target_is_directory=False,
                )
                subprocess.run(["git", "init", "-q"], cwd=root, check=True)
                subprocess.run(
                    [
                        "git",
                        "add",
                        "-f",
                        "evaluation/fixtures/antigravity/tracked-link.json",
                    ],
                    cwd=root,
                    check=True,
                )
                original_read_text = Path.read_text

                def reject_guarded_read(
                    path: Path,
                    *args: object,
                    **kwargs: object,
                ) -> str:
                    if path == guarded:
                        raise AssertionError("guarded symlink content was read")
                    return original_read_text(path, *args, **kwargs)

                with patch("pathlib.Path.read_text", new=reject_guarded_read):
                    errors = validate(root)

                self.assertIn(
                    "Unsafe tracked evaluation asset symlink: "
                    "evaluation/fixtures/antigravity/tracked-link.json",
                    errors,
                )

    def test_validator_rejects_guarded_asset_symlinked_ancestors_without_reading(
        self,
    ) -> None:
        for label in ("external", "ignored raw"):
            with self.subTest(target=label):
                temp, root = self.make_root(
                    nested_under_workspace=label == "external"
                )
                self.addCleanup(temp.cleanup)
                guarded = root / "evaluation/reports/tracked-report.md"
                guarded.parent.mkdir(parents=True, exist_ok=True)
                guarded.write_text("# Sanitized report\n", encoding="utf-8")
                subprocess.run(["git", "init", "-q"], cwd=root, check=True)
                subprocess.run(
                    ["git", "add", "-f", "evaluation/reports/tracked-report.md"],
                    cwd=root,
                    check=True,
                )

                target = (
                    Path(temp.name) / "external-reports"
                    if label == "external"
                    else root / ".semantic-runs/private-reports"
                )
                target.mkdir(parents=True)
                (target / guarded.name).write_text(
                    "Authorization: Bearer provider-secret\n",
                    encoding="utf-8",
                )
                shutil.rmtree(guarded.parent)
                self.require_symlink(
                    guarded.parent,
                    target,
                    target_is_directory=True,
                )
                original_read_text = Path.read_text

                def reject_guarded_read(
                    path: Path,
                    *args: object,
                    **kwargs: object,
                ) -> str:
                    if path == guarded:
                        raise AssertionError(
                            "guarded ancestor symlink content was read"
                        )
                    return original_read_text(path, *args, **kwargs)

                with patch("pathlib.Path.read_text", new=reject_guarded_read):
                    errors = validate(root)

                self.assertIn(
                    "Unsafe tracked evaluation asset symlink: "
                    "evaluation/reports (tracked asset: "
                    "evaluation/reports/tracked-report.md)",
                    errors,
                )

    def test_validator_guards_tracked_evaluation_reports(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        report = root / "evaluation/reports/leak.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "Authorization: Bearer provider-secret\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(
            ["git", "add", "-f", "evaluation/reports/leak.md"],
            cwd=root,
            check=True,
        )

        self.assertIn(
            "Unsafe tracked evaluation asset: evaluation/reports/leak.md",
            validate(root),
        )

    def test_validator_rejects_home_path_in_tracked_evaluation_asset(
        self,
    ) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        fixture = root / "evaluation/fixtures/antigravity/home-path.json"
        fixture.parent.mkdir(parents=True)
        fixture.write_text(
            '{"path": "/home/private-user/provider-output.json"}\n',
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(
            [
                "git",
                "add",
                "-f",
                "evaluation/fixtures/antigravity/home-path.json",
            ],
            cwd=root,
            check=True,
        )

        self.assertIn(
            "Unsafe tracked evaluation asset: "
            "evaluation/fixtures/antigravity/home-path.json",
            validate(root),
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
