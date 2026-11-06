"""Contract-driven helpers for Antigravity NDJSON streams."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import NoReturn

from evaluation.schema import JsonValue, StreamContract


_ARRAY_INDEX = re.compile(r"(?:0|[1-9][0-9]*)")
_MISSING = object()


@dataclass(frozen=True)
class TutorTurn:
    text: str
    event_count: int
    completed: bool


def _tokens(pointer: str) -> tuple[str, ...]:
    if pointer == "":
        return ()
    if not pointer.startswith("/"):
        raise ValueError("JSON Pointer must be empty or start with '/'")

    decoded: list[str] = []
    for raw_token in pointer[1:].split("/"):
        token: list[str] = []
        index = 0
        while index < len(raw_token):
            character = raw_token[index]
            if character != "~":
                token.append(character)
                index += 1
                continue
            if index + 1 >= len(raw_token) or raw_token[index + 1] not in {"0", "1"}:
                raise ValueError(f"malformed JSON Pointer escape in {pointer!r}")
            token.append("~" if raw_token[index + 1] == "0" else "/")
            index += 2
        decoded.append("".join(token))
    return tuple(decoded)


def _array_index(token: str) -> int:
    if not _ARRAY_INDEX.fullmatch(token):
        raise ValueError(f"JSON Pointer array token must be a canonical index, got {token!r}")
    return int(token)


def json_pointer_get(value: JsonValue, pointer: str) -> JsonValue:
    current = value
    for token in _tokens(pointer):
        if isinstance(current, dict):
            if token not in current:
                raise KeyError(token)
            current = current[token]
        elif isinstance(current, list):
            index = _array_index(token)
            if index >= len(current):
                raise IndexError(index)
            current = current[index]
        else:
            raise TypeError(
                f"cannot traverse JSON Pointer token {token!r} through "
                f"{type(current).__name__}"
            )
    return current


def json_pointer_set(
    value: JsonValue,
    pointer: str,
    replacement: JsonValue,
) -> JsonValue:
    tokens = _tokens(pointer)
    if not tokens:
        return copy.deepcopy(replacement)

    updated = copy.deepcopy(value)
    parent_pointer = (
        "/" + "/".join(_encode_token(token) for token in tokens[:-1])
        if len(tokens) > 1
        else ""
    )
    parent = json_pointer_get(updated, parent_pointer)
    token = tokens[-1]
    copied_replacement = copy.deepcopy(replacement)
    if isinstance(parent, dict):
        if token not in parent:
            raise KeyError(token)
        parent[token] = copied_replacement
    elif isinstance(parent, list):
        index = _array_index(token)
        if index >= len(parent):
            raise IndexError(index)
        parent[index] = copied_replacement
    else:
        raise TypeError(
            f"cannot set JSON Pointer token {token!r} on {type(parent).__name__}"
        )
    return updated


def _encode_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _reject_constant(name: str) -> NoReturn:
    raise ValueError(f"non-finite JSON number is not allowed: {name}")


def _reject_duplicates(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def parse_ndjson(data: bytes) -> tuple[dict[str, JsonValue], ...]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        line_number = data[: error.start].count(b"\n") + 1
        raise ValueError(f"invalid UTF-8 on line {line_number}: {error.reason}") from error

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    events: list[dict[str, JsonValue]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            raise ValueError(f"blank NDJSON event on line {line_number}")
        try:
            event = json.loads(
                line,
                object_pairs_hook=_reject_duplicates,
                parse_constant=_reject_constant,
            )
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"invalid JSON on line {line_number}: {error}") from error
        if not isinstance(event, dict):
            raise ValueError(
                f"NDJSON event on line {line_number} must be an object, "
                f"got {type(event).__name__}"
            )
        events.append(event)
    return tuple(events)


def request_line(contract: StreamContract, text: str) -> bytes:
    request = json_pointer_set(
        contract.request_template,
        contract.request_text_pointer,
        text,
    )
    return (
        json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _pointer_value(value: JsonValue, pointer: str) -> JsonValue | object:
    try:
        return json_pointer_get(value, pointer)
    except (KeyError, IndexError, TypeError):
        return _MISSING


def _exact_json_match(left: JsonValue, right: JsonValue) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _exact_json_match(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _exact_json_match(left[key], right[key]) for key in left
        )
    return left == right


def _merge_fragment(text: str, fragment: str) -> str:
    if not fragment or text.startswith(fragment):
        return text
    if fragment.startswith(text):
        return fragment
    return text + fragment


def collect_tutor_turn(
    events: Sequence[dict[str, JsonValue]],
    contract: StreamContract,
) -> TutorTurn:
    text = ""
    event_count = 0
    completed = False

    for event in events:
        event_count += 1
        for pointer in contract.output_text_pointers:
            fragment = _pointer_value(event, pointer)
            if fragment is _MISSING:
                continue
            if not isinstance(fragment, str):
                raise ValueError(
                    f"extracted text at {pointer!r} in event {event_count} must be a string"
                )
            text = _merge_fragment(text, fragment)

        completion = _pointer_value(event, contract.completion_pointer)
        if completion is not _MISSING and _exact_json_match(
            completion, contract.completion_value
        ):
            completed = True
            break

    return TutorTurn(text=text, event_count=event_count, completed=completed)
