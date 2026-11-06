from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from socratic_learn.errors import IntegrityError, UsageError
from socratic_learn.release import (
    current_platform,
    download_verified,
    parse_release_manifest,
    select_artifact,
)


class ReleaseTests(unittest.TestCase):
    def manifest(
        self,
        payload: bytes = b"binary",
        **artifact_overrides: object,
    ) -> bytes:
        artifact: dict[str, object] = {
            "platform": "windows",
            "architecture": "x86_64",
            "filename": "socratic-windows-x86_64.exe",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        artifact.update(artifact_overrides)
        return json.dumps(
            {
                "schema_version": 1,
                "version": "0.1.0",
                "artifacts": [artifact],
            }
        ).encode("utf-8")

    def parse(self, data: bytes) -> tuple[object, ...]:
        return parse_release_manifest(
            data,
            "https://example.invalid/releases/v0.1.0/",
        )

    def test_parse_and_select_exact_platform(self) -> None:
        artifact = select_artifact(self.parse(self.manifest()), "windows", "x86_64")

        self.assertEqual("0.1.0", artifact.version)
        self.assertEqual("socratic-windows-x86_64.exe", artifact.filename)
        self.assertEqual(
            "https://example.invalid/releases/v0.1.0/"
            "socratic-windows-x86_64.exe",
            artifact.url,
        )

    def test_parser_rejects_invalid_json_and_non_object_root(self) -> None:
        for data in (b"{", b"[]"):
            with self.subTest(data=data), self.assertRaises(IntegrityError):
                self.parse(data)

    def test_parser_requires_exact_keys(self) -> None:
        document = json.loads(self.manifest())
        cases = (
            (document | {"extra": 1}, "extra"),
            ({"schema_version": 1, "version": "0.1.0"}, "artifacts"),
        )
        for value, expected in cases:
            with self.subTest(expected=expected), self.assertRaisesRegex(
                IntegrityError, expected
            ):
                self.parse(json.dumps(value).encode())

        document["artifacts"][0]["extra"] = 1
        with self.assertRaisesRegex(IntegrityError, "extra"):
            self.parse(json.dumps(document).encode())

    def test_parser_rejects_boolean_integer_fields(self) -> None:
        for field in ("schema_version", "size"):
            document = json.loads(self.manifest())
            target = document if field == "schema_version" else document["artifacts"][0]
            target[field] = True
            with self.subTest(field=field), self.assertRaisesRegex(
                IntegrityError, field
            ):
                self.parse(json.dumps(document).encode())

    def test_parser_rejects_wrong_types_and_empty_artifacts(self) -> None:
        documents = (
            {"schema_version": 1, "version": 1, "artifacts": []},
            {"schema_version": 1, "version": "0.1.0", "artifacts": {}},
            {"schema_version": 1, "version": "0.1.0", "artifacts": []},
            {"schema_version": 1, "version": "0.1.0", "artifacts": [None]},
        )
        for document in documents:
            with self.subTest(document=document), self.assertRaises(IntegrityError):
                self.parse(json.dumps(document).encode())

    def test_parser_enforces_semantic_versions(self) -> None:
        valid = ("0.1.0", "1.0.0-alpha.1", "2.3.4+build.7")
        invalid = ("1.0", "v1.0.0", "01.0.0", "1.0.0-", "1.0.0-01")
        for version in valid:
            document = json.loads(self.manifest())
            document["version"] = version
            with self.subTest(version=version):
                self.parse(json.dumps(document).encode())
        for version in invalid:
            document = json.loads(self.manifest())
            document["version"] = version
            with self.subTest(version=version), self.assertRaisesRegex(
                IntegrityError, "version"
            ):
                self.parse(json.dumps(document).encode())

    def test_parser_rejects_unsafe_filenames(self) -> None:
        for filename in (
            "",
            ".",
            "..",
            "sub/file.exe",
            r"sub\file.exe",
            "C:file.exe",
            "file\x00.exe",
            "file\n.exe",
        ):
            with self.subTest(filename=filename), self.assertRaisesRegex(
                IntegrityError, "filename"
            ):
                self.parse(self.manifest(filename=filename))

    def test_parser_rejects_nonportable_filename_classes(self) -> None:
        cases = {
            "reserved device basename": (
                "CON",
                "con.exe",
                "PRN.zip",
                "aux",
                "NUL.tar.gz",
                "COM1",
                "com9.bin",
                "LPT1",
                "lPt9.txt",
            ),
            "Windows-forbidden punctuation": (
                "bad<name.exe",
                "bad>name.exe",
                "bad:name.exe",
                'bad"name.exe',
                "bad/name.exe",
                r"bad\name.exe",
                "bad|name.exe",
                "bad?name.exe",
                "bad*name.exe",
            ),
            "trailing space or period": (
                "artifact.exe ",
                "artifact.exe.",
            ),
            "Unicode control character": (
                "artifact\u0085.exe",
                "artifact\u009f.exe",
            ),
        }
        for rejected_class, filenames in cases.items():
            for filename in filenames:
                with (
                    self.subTest(rejected_class=rejected_class, filename=filename),
                    self.assertRaisesRegex(IntegrityError, "filename"),
                ):
                    self.parse(self.manifest(filename=filename))

    def test_parser_accepts_portable_filename(self) -> None:
        filename = "socratic-learn_1.2.3-café(x86-64).exe"

        artifact = self.parse(self.manifest(filename=filename))[0]

        self.assertEqual(filename, artifact.filename)

    def test_schema_rejects_same_nonportable_filename_classes(self) -> None:
        schema = json.loads(
            (Path(__file__).parents[1] / "release-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
        filename_schema = schema["properties"]["artifacts"]["items"]["properties"][
            "filename"
        ]
        allowed_pattern = re.compile(filename_schema["pattern"])
        reserved_pattern = re.compile(filename_schema["not"]["pattern"])
        cases = (
            "CON",
            "con.exe",
            "COM9.zip",
            "Lpt1.bin",
            "bad<name.exe",
            "bad>name.exe",
            "bad:name.exe",
            'bad"name.exe',
            "bad/name.exe",
            r"bad\name.exe",
            "bad|name.exe",
            "bad?name.exe",
            "bad*name.exe",
            "artifact.exe ",
            "artifact.exe.",
            "artifact\u0085.exe",
            "artifact\u009f.exe",
        )
        for filename in cases:
            with self.subTest(filename=filename):
                accepted = (
                    allowed_pattern.fullmatch(filename) is not None
                    and reserved_pattern.search(filename) is None
                )
                self.assertFalse(accepted)

        self.assertIsNotNone(
            allowed_pattern.fullmatch("socratic-learn_1.2.3-café(x86-64).exe")
        )

    def test_parser_rejects_nonpositive_size_and_malformed_hash(self) -> None:
        for size in (0, -1):
            with self.subTest(size=size), self.assertRaisesRegex(
                IntegrityError, "size"
            ):
                self.parse(self.manifest(size=size))
        for digest in ("A" * 64, "a" * 63, "g" * 64):
            with self.subTest(digest=digest), self.assertRaisesRegex(
                IntegrityError, "sha256"
            ):
                self.parse(self.manifest(sha256=digest))

    def test_parser_rejects_duplicate_platform_architecture_pair(self) -> None:
        document = json.loads(self.manifest())
        duplicate = dict(document["artifacts"][0])
        duplicate["filename"] = "duplicate.exe"
        document["artifacts"].append(duplicate)

        with self.assertRaisesRegex(IntegrityError, "duplicate"):
            self.parse(json.dumps(document).encode())

    def test_current_platform_normalizes_supported_values(self) -> None:
        cases = (
            ("win32", "AMD64", ("windows", "x86_64")),
            ("linux", "x86_64", ("linux", "x86_64")),
            ("darwin", "x64", ("macos", "x86_64")),
        )
        for system, machine, expected in cases:
            with (
                self.subTest(system=system, machine=machine),
                patch("socratic_learn.release.sys.platform", system),
                patch("socratic_learn.release.platform.machine", return_value=machine),
            ):
                self.assertEqual(expected, current_platform())

    def test_current_platform_rejects_unsupported_architecture_with_remediation(
        self,
    ) -> None:
        with (
            patch("socratic_learn.release.sys.platform", "linux"),
            patch("socratic_learn.release.platform.machine", return_value="arm64"),
            self.assertRaises(UsageError) as raised,
        ):
            current_platform()

        self.assertEqual("pipx install socratic-learn", raised.exception.remediation)

    def test_select_artifact_rejects_missing_pair(self) -> None:
        with self.assertRaises(UsageError):
            select_artifact(self.parse(self.manifest()), "linux", "x86_64")

    def test_download_verified_streams_and_publishes(self) -> None:
        payload = b"a" * 200_000
        artifact = self.parse(self.manifest(payload))[0]
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / artifact.filename

            result = download_verified(
                artifact,
                destination,
                opener=lambda url: io.BytesIO(payload),
            )

            self.assertEqual(destination, result)
            self.assertEqual(payload, destination.read_bytes())
            self.assertEqual([destination], list(Path(temporary).iterdir()))

    def test_hash_mismatch_preserves_no_destination(self) -> None:
        artifact = self.parse(self.manifest(b"expected"))[0]
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / artifact.filename
            with self.assertRaises(IntegrityError):
                download_verified(
                    artifact,
                    destination,
                    opener=lambda url: io.BytesIO(b"tampered"),
                )
            self.assertFalse(destination.exists())
            self.assertEqual([], list(Path(temporary).iterdir()))

    def test_size_mismatch_preserves_existing_destination(self) -> None:
        artifact = self.parse(self.manifest(b"expected"))[0]
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / artifact.filename
            destination.write_bytes(b"existing")

            with self.assertRaisesRegex(IntegrityError, "size"):
                download_verified(
                    artifact,
                    destination,
                    opener=lambda url: io.BytesIO(b"short"),
                )

            self.assertEqual(b"existing", destination.read_bytes())
            self.assertEqual([destination], list(Path(temporary).iterdir()))

    def test_opener_failure_preserves_existing_destination(self) -> None:
        artifact = self.parse(self.manifest())[0]
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / artifact.filename
            destination.write_bytes(b"existing")

            def fail(url: str) -> io.BytesIO:
                raise OSError("network failure")

            with self.assertRaises(OSError):
                download_verified(artifact, destination, opener=fail)

            self.assertEqual(b"existing", destination.read_bytes())
            self.assertEqual([destination], list(Path(temporary).iterdir()))

    def test_replace_failure_removes_only_temporary_file(self) -> None:
        payload = b"binary"
        artifact = self.parse(self.manifest(payload))[0]
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / artifact.filename
            destination.write_bytes(b"existing")

            with (
                patch("socratic_learn.release.os.replace", side_effect=OSError("busy")),
                self.assertRaises(OSError),
            ):
                download_verified(
                    artifact,
                    destination,
                    opener=lambda url: io.BytesIO(payload),
                )

            self.assertEqual(b"existing", destination.read_bytes())
            self.assertEqual([destination], list(Path(temporary).iterdir()))

    def test_download_opens_temporary_file_exclusively(self) -> None:
        payload = b"binary"
        artifact = self.parse(self.manifest(payload))[0]
        flags: list[int] = []
        real_open = os.open

        def recording_open(path: str, open_flags: int, mode: int = 0o777) -> int:
            flags.append(open_flags)
            return real_open(path, open_flags, mode)

        with tempfile.TemporaryDirectory() as temporary:
            with patch("socratic_learn.release.os.open", side_effect=recording_open):
                download_verified(
                    artifact,
                    Path(temporary) / artifact.filename,
                    opener=lambda url: io.BytesIO(payload),
                )

        self.assertTrue(any(open_flags & os.O_EXCL for open_flags in flags))


if __name__ == "__main__":
    unittest.main()
