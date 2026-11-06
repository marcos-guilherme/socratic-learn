from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation.sanitize import (
    RedactionRule,
    assert_tracked_safe,
    sanitize_json,
    sanitize_text,
    write_private,
)


def _symlinks_supported() -> bool:
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary).resolve()
        target = base / "target"
        target.mkdir()
        link = base / "link"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            return False
        return link.is_symlink()


class EvaluationSanitizeTests(unittest.TestCase):
    def test_recursive_redaction_preserves_json_shape(self) -> None:
        value = {
            "session_id": "provider-secret-id",
            "nested": ["C:/Users/Marcos/private", {"token": "Bearer abc123"}],
        }
        rules = (
            RedactionRule("provider-secret-id", "REDACTED_SESSION_ID"),
            RedactionRule("C:/Users/Marcos/private", "REDACTED_RUN_ROOT"),
            RedactionRule("Bearer abc123", "REDACTED_SECRET"),
        )
        self.assertEqual(
            {
                "session_id": "REDACTED_SESSION_ID",
                "nested": ["REDACTED_RUN_ROOT", {"token": "REDACTED_SECRET"}],
            },
            sanitize_json(value, rules),
        )

    def test_tracked_text_rejects_secret_and_absolute_home(self) -> None:
        with self.assertRaises(ValueError):
            assert_tracked_safe(
                "authorization: Bearer abc123\nC:\\Users\\Marcos\\private",
                forbidden_literals=("abc123",),
            )

    def test_private_write_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with self.assertRaises(ValueError):
                write_private(root.parent / "escape.txt", b"x", private_root=root)

    def test_rejects_empty_literal(self) -> None:
        with self.assertRaises(ValueError):
            sanitize_text("hello", (RedactionRule("", "x"),))

    def test_single_pass_longest_first_replacement_not_reprocessed(self) -> None:
        rules = (RedactionRule("A", "B"), RedactionRule("B", "C"))
        self.assertEqual("B", sanitize_text("A", rules))
        rules2 = (
            RedactionRule("abcd", "X"),
            RedactionRule("bc", "Y"),
        )
        self.assertEqual("X", sanitize_text("abcd", rules2))

    def test_conflicting_duplicate_literals_rejected(self) -> None:
        with self.assertRaises(ValueError):
            sanitize_text(
                "xx",
                (RedactionRule("x", "a"), RedactionRule("x", "b")),
            )

    def test_dict_keys_sanitized(self) -> None:
        rules = (RedactionRule("Bearer abc", "REDACTED_SECRET"),)
        self.assertEqual(
            {"REDACTED_SECRET": 1},
            sanitize_json({"Bearer abc": 1}, rules),
        )

    def test_dict_key_collision_after_redaction_rejected(self) -> None:
        # Same-length literals tie-break lexicographically; both map second char to Z.
        rules = (RedactionRule("a", "Z"), RedactionRule("b", "Z"))
        with self.assertRaises(ValueError):
            sanitize_json({"pa": 1, "pb": 2}, rules)

    def test_unsupported_tuple_rejected(self) -> None:
        with self.assertRaises(TypeError):
            sanitize_json((1, 2), ())

    def test_tracked_rejects_prefixed_api_key_assignment(self) -> None:
        with self.assertRaises(ValueError):
            assert_tracked_safe("export OPENAI_API_KEY=sk-test", forbidden_literals=())

    def test_tracked_rejects_credential_assignment_and_json_key_shapes(self) -> None:
        samples = (
            "export OPENAI_API_KEY=sk-test",
            "AWS_SECRET_ACCESS_KEY=ABCDEF",
            "AZURE_OPENAI_API_KEY=secret",
            "MY_PROVIDER_TOKEN=abc123",
            "OPENAI_API_KEY: value",
            '{"OPENAI_API_KEY": "value"}',
        )
        for line in samples:
            with self.subTest(line=line):
                with self.assertRaises(ValueError):
                    assert_tracked_safe(line, forbidden_literals=())

    def test_tracked_allows_benign_non_credentials(self) -> None:
        benign = (
            "max_tokens=100",
            "monkey=1",
            "We should discuss the token budget without any assignment syntax.",
            "MAX_TOKENS=128",
        )
        for line in benign:
            with self.subTest(line=line):
                assert_tracked_safe(line, forbidden_literals=())

    def test_write_private_rejects_destination_is_private_root(self) -> None:
        import evaluation.sanitize as sanitize_module

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with patch.object(sanitize_module.tempfile, "mkstemp") as mock_mkstemp:
                with self.assertRaises(ValueError):
                    write_private(root, b"x", private_root=root)
                mock_mkstemp.assert_not_called()
            with patch.object(sanitize_module.tempfile, "mkstemp") as mock_mkstemp:
                with self.assertRaises(ValueError):
                    write_private(Path("."), b"x", private_root=root)
                mock_mkstemp.assert_not_called()

    def test_write_private_closes_fd_on_chmod_failure(self) -> None:
        """chmod failure must close the mkstemp fd and remove the temp path."""
        real_chmod = os.chmod
        close_calls: list[int] = []
        real_close = os.close

        def tracking_close(fd: int) -> None:
            close_calls.append(fd)
            return real_close(fd)

        def selective_chmod(path: str | os.PathLike[str], mode: int) -> None:
            if Path(path).name.startswith(".private_write_"):
                raise OSError("chmod denied")
            return real_chmod(path, mode)

        import evaluation.sanitize as sanitize_module

        real_mkstemp = tempfile.mkstemp
        captured: dict[str, int | str] = {}

        def capture_mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
            fd, path = real_mkstemp(*args, **kwargs)
            captured["fd"] = fd
            captured["path"] = path
            return fd, path

        with (
            patch.object(sanitize_module.os, "chmod", side_effect=selective_chmod),
            patch.object(sanitize_module.os, "close", side_effect=tracking_close),
            patch.object(sanitize_module.tempfile, "mkstemp", side_effect=capture_mkstemp),
        ):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                dest = root / "out.bin"
                with self.assertRaises(OSError):
                    write_private(dest, b"data", private_root=root)
                tmp_path = str(captured["path"])
                mk_fd = captured["fd"]
                self.assertIn(mk_fd, close_calls)
                self.assertFalse(os.path.lexists(tmp_path))
                parent = Path(tmp_path).parent.resolve()
                self.assertEqual(parent, root)
                self.assertFalse(
                    any(n.name.startswith(".private_write_") for n in parent.iterdir()),
                    f"unexpected temp in {parent}: {list(parent.iterdir())}",
                )

    @patch("evaluation.sanitize.os.replace")
    def test_write_private_cleans_temp_on_replace_failure(self, mock_replace: object) -> None:
        mock_replace.side_effect = OSError("replace failed")

        import evaluation.sanitize as sanitize_module

        real_mkstemp = tempfile.mkstemp
        tmp_paths: list[str] = []

        def capture_mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
            fd, path = real_mkstemp(*args, **kwargs)
            tmp_paths.append(path)
            return fd, path

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            dest = root / "out.bin"
            with patch.object(sanitize_module.tempfile, "mkstemp", side_effect=capture_mkstemp):
                with self.assertRaises(OSError):
                    write_private(dest, b"payload", private_root=root)
            self.assertEqual(1, len(tmp_paths))
            tmp_path = Path(tmp_paths[0]).resolve()
            self.assertFalse(os.path.lexists(tmp_path))
            self.assertEqual(tmp_path.parent, root)
            self.assertFalse(
                any(n.name.startswith(".private_write_") for n in root.iterdir()),
                f"unexpected temp in {root}: {list(root.iterdir())}",
            )
            self.assertFalse(dest.exists())
            self.assertEqual(list(root.iterdir()), [])

    @unittest.skipUnless(_symlinks_supported(), "symlinks unavailable")
    def test_resolves_symlink_escape_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as outer:
            outer_path = Path(outer).resolve()
            safe_root = outer_path / "vault"
            safe_root.mkdir()
            outside = outer_path / "outside"
            outside.mkdir()
            link = safe_root / "escape"
            link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                write_private(link / "leak.bin", b"x", private_root=safe_root.resolve())
