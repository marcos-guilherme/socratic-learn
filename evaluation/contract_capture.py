"""Capture, sanitize, and publish the installed Antigravity stream-json contract.

The request envelope is always supplied by the operator from first-party material; this module
never synthesizes envelope fields. Raw probe material stays under a private, ignored root.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from subprocess import CompletedProcess

from evaluation.sanitize import RedactionRule, assert_tracked_safe, sanitize_json, write_private
from evaluation.schema import JsonValue, canonical_json, load_stream_contract

MARKER = "STREAM_CONTRACT_OK"
PROBE_TIMEOUT_SECONDS = 360
BLOCKED_EXIT_CODE = 2
VALID_MESSAGE = "Antigravity stream contract fixture is valid."

_VERSION = re.compile(r"\d+\.\d+\.\d+(?:[-+.][0-9A-Za-z.-]+)?")
_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|tmp|var|private)/)")


class ContractCaptureError(ValueError):
    """The probe or fixture cannot establish an observed contract."""


def capture_contract(
    executable: str,
    model: str,
    request_line: bytes,
    raw_root: Path,
    *,
    completion_pointer: str,
    completion_value: JsonValue,
    output_text_pointers: Sequence[str] | None = None,
    run: Callable[..., CompletedProcess[bytes]] = subprocess.run,
) -> dict[str, JsonValue]:
    request, request_pointer = _parse_request(request_line)
    _require_pointer_syntax(completion_pointer, "completion pointer")
    for pointer in output_text_pointers or ():
        _require_pointer_syntax(pointer, "output text pointer")

    raw_root = Path(raw_root).absolute()
    raw_root.mkdir(parents=True, exist_ok=True)
    workspace = raw_root / "workspace"
    workspace.mkdir(exist_ok=True)
    argv = [
        executable,
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--model",
        model,
        "--sandbox",
        "--disable-slash-commands",
        "--print-timeout",
        "300s",
        "--log-file",
        str(raw_root / "antigravity.log"),
    ]
    write_private(raw_root / "request.ndjson", request_line, private_root=raw_root)
    write_private(raw_root / "argv.json", canonical_json(argv), private_root=raw_root)

    try:
        completed = run(
            argv,
            input=request_line,
            capture_output=True,
            cwd=str(workspace),
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ContractCaptureError(f"probe did not complete: {type(error).__name__}") from error

    stdout = completed.stdout or b""
    write_private(raw_root / "stdout.ndjson", stdout, private_root=raw_root)
    write_private(raw_root / "stderr.txt", completed.stderr or b"", private_root=raw_root)
    if completed.returncode != 0:
        raise ContractCaptureError(f"probe exited with code {completed.returncode}")

    events = _parse_output(stdout)
    if not any(_matches(event, completion_pointer, completion_value) for event in events):
        raise ContractCaptureError("no output event carries the completion pointer/value")
    observed_pointers = _marker_pointers(events)
    if not observed_pointers:
        raise ContractCaptureError(f"no output event text contains {MARKER}")
    if output_text_pointers is None:
        output_pointers = observed_pointers
    else:
        output_pointers = list(output_text_pointers)
        if not output_pointers or not set(output_pointers) <= set(observed_pointers):
            raise ContractCaptureError(f"output text pointers do not yield {MARKER} in the stream")

    return {
        "antigravity_version": _recorded_version(raw_root),
        "model_identifier": model,
        "request_text_pointer": request_pointer,
        "output_text_pointers": output_pointers,
        "completion_pointer": completion_pointer,
        "completion_value": completion_value,
        "request_template": request,
        "sample_output_events": events,
    }


def publish_contract_fixture(
    capture: Mapping[str, JsonValue],
    destination: Path,
    *,
    rules: Sequence[RedactionRule],
) -> Path:
    fixture = {
        "schema_version": 1,
        "antigravity_version": capture["antigravity_version"],
        "model_identifier": capture["model_identifier"],
        "request_text_pointer": capture["request_text_pointer"],
        "output_text_pointers": capture["output_text_pointers"],
        "completion_pointer": capture["completion_pointer"],
        "completion_value": capture["completion_value"],
        "request_template": capture["request_template"],
        "sample_output_events": capture["sample_output_events"],
    }
    sanitized = sanitize_json(fixture, rules)
    _check_consistency(sanitized)  # type: ignore[arg-type]
    data = canonical_json(sanitized)
    _assert_safe(data.decode("utf-8"), sanitized, [rule.literal for rule in rules])

    destination = Path(destination).absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_private(destination, data, private_root=destination.parent)
    load_stream_contract(destination)
    return destination


def select_model(listing: str, choice: str) -> str:
    listed = {
        line.split("\t", 1)[0].strip()
        for line in listing.splitlines()
        if "\t" in line and line.split("\t", 1)[0].strip()
    }
    if choice not in listed:
        raise ContractCaptureError("model must be an exact first-column identifier from agy models")
    return choice


def validate_fixture(path: Path) -> None:
    try:
        contract = load_stream_contract(Path(path))
    except ValueError as error:
        raise ContractCaptureError(str(error)) from error
    if not _VERSION.fullmatch(contract.antigravity_version):
        raise ContractCaptureError("antigravity_version must be an observed CLI version")
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    _check_consistency(document)
    try:
        _assert_safe(json.dumps(document, ensure_ascii=False, indent=2), document, ())
    except ValueError as error:
        raise ContractCaptureError(f"fixture is not tracked-safe: {error}") from error


def resolve_pointer(document: JsonValue, pointer: str) -> JsonValue:
    _require_pointer_syntax(pointer, "pointer")
    current = document
    for token in pointer.split("/")[1:] if pointer else ():
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list) and key.isdigit() and int(key) < len(current):
            current = current[int(key)]
        else:
            raise KeyError(pointer)
    return current


def _require_pointer_syntax(pointer: object, label: str) -> None:
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise ContractCaptureError(f"{label} must be a JSON Pointer")


def _matches(document: JsonValue, pointer: str, expected: JsonValue) -> bool:
    try:
        return resolve_pointer(document, pointer) == expected
    except KeyError:
        return False


def _string_leaves(value: JsonValue, pointer: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield pointer, value
    elif isinstance(value, dict):
        for key, item in value.items():
            token = key.replace("~", "~0").replace("/", "~1")
            yield from _string_leaves(item, f"{pointer}/{token}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _string_leaves(item, f"{pointer}/{index}")


def _reject_duplicates(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ContractCaptureError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(name: str) -> JsonValue:
    raise ContractCaptureError(f"non-finite JSON number: {name}")


def _load_json(text: str, label: str) -> JsonValue:
    try:
        return json.loads(
            text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant
        )
    except json.JSONDecodeError as error:
        raise ContractCaptureError(f"{label} is not valid JSON") from error


def _parse_request(request_line: bytes) -> tuple[dict[str, JsonValue], str]:
    try:
        text = request_line.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractCaptureError("request must be UTF-8") from error
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) != 1 or not text.endswith("\n"):
        raise ContractCaptureError("request must be exactly one newline-terminated JSON line")
    request = _load_json(lines[0], "request")
    if not isinstance(request, dict):
        raise ContractCaptureError("request must be a JSON object")
    pointers = [pointer for pointer, value in _string_leaves(request) if MARKER in value]
    if len(pointers) != 1 or resolve_pointer(request, pointers[0]) != MARKER:
        raise ContractCaptureError(f"request must contain exactly one string equal to {MARKER}")
    return request, pointers[0]


def _parse_output(stdout: bytes) -> list[dict[str, JsonValue]]:
    try:
        text = stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContractCaptureError("probe stdout is not UTF-8") from error
    events: list[dict[str, JsonValue]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        event = _load_json(line, f"stdout line {number}")
        if not isinstance(event, dict):
            raise ContractCaptureError(f"stdout line {number} is not a JSON object")
        events.append(event)
    if not events:
        raise ContractCaptureError("probe stdout contains no JSON events")
    return events


def _marker_pointers(events: Sequence[JsonValue]) -> list[str]:
    pointers: list[str] = []
    for event in events:
        for pointer, value in _string_leaves(event):
            if MARKER in value and pointer not in pointers:
                pointers.append(pointer)
    return pointers


def _recorded_version(raw_root: Path) -> str:
    path = raw_root / "version.txt"
    if path.is_file():
        version = path.read_text(encoding="utf-8-sig").strip()
        if version:
            return version
    return "unknown"


def _check_consistency(document: Mapping[str, JsonValue]) -> None:
    request = document["request_template"]
    events = document["sample_output_events"]
    if not isinstance(events, list):
        raise ContractCaptureError("sample_output_events must be an array")
    if not _matches(request, str(document["request_text_pointer"]), MARKER):
        raise ContractCaptureError(f"request_text_pointer does not resolve to {MARKER}")
    completion_pointer = str(document["completion_pointer"])
    if not any(_matches(e, completion_pointer, document["completion_value"]) for e in events):
        raise ContractCaptureError("no sample event carries the completion pointer/value")
    pointers = document["output_text_pointers"]
    if not isinstance(pointers, list) or not pointers:
        raise ContractCaptureError("output_text_pointers must be a non-empty array")
    for pointer in pointers:
        texts = []
        for event in events:
            try:
                value = resolve_pointer(event, str(pointer))
            except KeyError:
                continue
            if isinstance(value, str):
                texts.append(value)
        if not any(MARKER in text for text in texts):
            raise ContractCaptureError(f"output pointer {pointer!r} never yields {MARKER}")


def _assert_safe(text: str, document: JsonValue, forbidden: Sequence[str]) -> None:
    assert_tracked_safe(text, forbidden_literals=forbidden)
    for pointer, value in _string_leaves(document):
        assert_tracked_safe(value, forbidden_literals=forbidden)
        assert_tracked_safe(pointer, forbidden_literals=forbidden)
        if _ABSOLUTE_PATH.match(value) or _UUID.search(value):
            raise ContractCaptureError("tracked fixture contains an absolute path or raw identifier")


def _observed_redactions(events: Sequence[JsonValue]) -> tuple[RedactionRule, ...]:
    rules: dict[str, str] = {}
    for event in events:
        for _, value in _string_leaves(event):
            for identifier in _UUID.findall(value):
                rules.setdefault(identifier, "REDACTED_ID")
            if _ABSOLUTE_PATH.match(value):
                rules.setdefault(value, "REDACTED_PATH")
    for root in (Path.home(), Path(__file__).resolve().parents[1]):
        for form in (str(root), root.as_posix()):
            rules.setdefault(form, "REDACTED_PATH")
    return tuple(RedactionRule(literal, replacement) for literal, replacement in rules.items())


def _read_private(path: Path, label: str) -> str:
    if not path.is_file():
        raise ContractCaptureError(f"missing {label}: run the documented discovery steps first")
    return path.read_text(encoding="utf-8-sig")


def _command_select_model(args: argparse.Namespace, prompt: Callable[[str], str]) -> None:
    listing = _read_private(Path(args.models_file), "models listing")
    model = select_model(listing, prompt("Exact model identifier from agy models: ").strip())
    output = Path(args.output).absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    write_private(output, (model + "\n").encode("utf-8"), private_root=output.parent)
    print(f"Selected model: {model}")


def _command_discover(args: argparse.Namespace, prompt: Callable[[str], str]) -> None:
    raw_root = Path(args.raw_root).absolute()
    raw_root.mkdir(parents=True, exist_ok=True)
    source = prompt("First-party source of the request example: ").strip()
    if not source:
        raise ContractCaptureError("a first-party source is required")
    request_line = (prompt("One-line request with user text STREAM_CONTRACT_OK: ").strip() + "\n")
    _, observed_pointer = _parse_request(request_line.encode("utf-8"))
    request_pointer = prompt(f"JSON Pointer to {MARKER} in the request: ").strip()
    if request_pointer != observed_pointer:
        raise ContractCaptureError("request pointer does not resolve to the marker")
    output_pointers = [
        pointer.strip()
        for pointer in prompt("Output text JSON Pointer(s), comma-separated: ").split(",")
        if pointer.strip()
    ]
    if not output_pointers:
        raise ContractCaptureError("at least one output text pointer is required")
    for pointer in output_pointers:
        _require_pointer_syntax(pointer, "output text pointer")
    completion_pointer = prompt("JSON Pointer marking the completed output turn: ").strip()
    _require_pointer_syntax(completion_pointer, "completion pointer")
    completion_value = _load_json(prompt("JSON value at that pointer: ").strip(), "completion value")
    discovery = {
        "source": source,
        "request_line": request_line,
        "request_text_pointer": request_pointer,
        "output_text_pointers": output_pointers,
        "completion_pointer": completion_pointer,
        "completion_value": completion_value,
    }
    write_private(raw_root / "discovery.json", canonical_json(discovery), private_root=raw_root)
    print("Discovery recorded privately.")


def _command_capture(args: argparse.Namespace) -> None:
    raw_root = Path(args.raw_root).absolute()
    discovery = _load_json(_read_private(raw_root / "discovery.json", "discovery"), "discovery")
    if not isinstance(discovery, dict):
        raise ContractCaptureError("discovery must be a JSON object")
    _read_private(raw_root / "version.txt", "agy --version output")
    _read_private(raw_root / "help.txt", "agy --help output")
    model = select_model(
        _read_private(raw_root / "models.txt", "agy models output"),
        _read_private(Path(args.model_file), "selected model").strip(),
    )
    output_pointers = discovery.get("output_text_pointers")
    if not isinstance(output_pointers, list) or not all(isinstance(p, str) for p in output_pointers):
        raise ContractCaptureError("discovery must record output text pointers")
    captured = capture_contract(
        args.executable,
        model,
        str(discovery["request_line"]).encode("utf-8"),
        raw_root,
        completion_pointer=str(discovery["completion_pointer"]),
        completion_value=discovery["completion_value"],
        output_text_pointers=output_pointers,
    )
    if captured["request_text_pointer"] != discovery["request_text_pointer"]:
        raise ContractCaptureError("captured request pointer differs from discovery")
    events = captured["sample_output_events"]
    fixture = publish_contract_fixture(
        captured,
        Path(args.fixture),
        rules=_observed_redactions(events if isinstance(events, list) else []),
    )
    validate_fixture(fixture)
    print(f"Published sanitized fixture: {Path(args.fixture).as_posix()}")


def main(argv: Sequence[str] | None = None, *, prompt: Callable[[str], str] = input) -> int:
    parser = argparse.ArgumentParser(prog="python -m evaluation.contract_capture")
    commands = parser.add_subparsers(dest="command", required=True)
    select = commands.add_parser("select-model")
    select.add_argument("--models-file", required=True)
    select.add_argument("--output", required=True)
    discover = commands.add_parser("discover")
    discover.add_argument("--raw-root", required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("--raw-root", required=True)
    capture.add_argument("--model-file", required=True)
    capture.add_argument("--fixture", required=True)
    capture.add_argument("--executable", default="agy")
    validate = commands.add_parser("validate-fixture")
    validate.add_argument("fixture")
    args = parser.parse_args(argv)

    try:
        if args.command == "select-model":
            _command_select_model(args, prompt)
        elif args.command == "discover":
            _command_discover(args, prompt)
        elif args.command == "capture":
            _command_capture(args)
        else:
            validate_fixture(Path(args.fixture))
            print(VALID_MESSAGE)
    except (ContractCaptureError, ValueError, KeyError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return BLOCKED_EXIT_CODE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
