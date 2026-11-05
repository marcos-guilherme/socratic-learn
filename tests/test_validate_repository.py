from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests.validate_repository import main, validate

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
            ".cursor/skills/learning-tutor/SKILL.md",
            "adapters/cursor/README.md",
            "adapters/claude-code/CLAUDE.md",
            "adapters/pi/skills/learning-tutor/SKILL.md",
            "workspace/.gitkeep",
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# file\n", encoding="utf-8")
        skill = (
            "---\n"
            "name: learning-tutor\n"
            "description: Conducts structured learning sessions.\n"
            "---\n\n# Learning Tutor\n"
        )
        (root / ".cursor/skills/learning-tutor/SKILL.md").write_text(
            skill, encoding="utf-8"
        )
        (root / "adapters/pi/skills/learning-tutor/SKILL.md").write_text(
            skill, encoding="utf-8"
        )
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

    def test_pedagogy_defines_responsive_socratic_dialogue(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "core/pedagogy.md").read_text(encoding="utf-8").lower()
        start = "## responsive socratic dialogue"
        end = "## active application"
        self.assertIn(start, text, "Missing canonical Socratic section")
        self.assertIn(end, text, "Missing section boundary after Socratic contract")
        section = text.split(start, 1)[1].split(end, 1)[0]
        section = " ".join(section.split())

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
            "mathematics and ai applications": (
                "for mathematics and ai",
                "why does this work?",
                "which hypothesis is necessary?",
                "what evidence would refute the claim?",
                "what changes when this variable or condition varies?",
                "how does another approach compare?",
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
        expected = (
            "# Session: YYYY-MM-DD — Topic",
            "## Outcome",
            "## Diagnostic evidence",
            "## Approved dependency path",
            "## Concepts established",
            "## Application evidence",
            "## Remaining gaps",
            "## Next step",
            "## Sources",
        )
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
            actual = tuple(line for line in text.splitlines() if line.startswith("#"))
            with self.subTest(source=source):
                self.assertEqual(expected, actual)

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

    def test_missing_required_file_fails(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / "AGENTS.md").unlink()
        self.assertTrue(any("AGENTS.md" in error for error in validate(root)))

    def test_broken_relative_markdown_link_fails(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / "README.md").write_text("[Missing](missing.md)\n", encoding="utf-8")
        self.assertTrue(any("missing.md" in error for error in validate(root)))

    def test_fenced_code_is_ignored_for_links_and_private_markers(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / "README.md").write_text(
            "```markdown\n[Missing](missing.md)\nPRIVATE_LEARNER_DATA\n```\n",
            encoding="utf-8",
        )
        self.assertEqual([], validate(root))

    def test_markdown_link_with_optional_title_passes(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        (root / "guide.md").write_text("# Guide\n", encoding="utf-8")
        (root / "README.md").write_text(
            '[Guide](guide.md "Guide")\n', encoding="utf-8"
        )
        self.assertEqual([], validate(root))

    def test_invalid_skill_frontmatter_fails(self) -> None:
        temp, root = self.make_root()
        self.addCleanup(temp.cleanup)
        skill = root / ".cursor/skills/learning-tutor/SKILL.md"
        skill.write_text("---\nname: Learning Tutor\n---\n", encoding="utf-8")
        self.assertTrue(any("frontmatter" in error for error in validate(root)))

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
        (root / "README.md").write_text(
            "The PRIVATE_LEARNER_DATA marker identifies private records.\n",
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


if __name__ == "__main__":
    unittest.main()
