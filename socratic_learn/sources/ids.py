"""Stable SHA-256 source identifiers."""

from __future__ import annotations

import hashlib


def source_id_for_local(raw: bytes) -> str:
    return hashlib.sha256(b"local-pdf\0" + raw).hexdigest()


def source_id_for_url(canonical_url: str, raw: bytes) -> str:
    payload = b"url\0" + canonical_url.encode("utf-8") + b"\0" + raw
    return hashlib.sha256(payload).hexdigest()
