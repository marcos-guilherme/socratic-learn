"""Orchestrate source retrieval, extraction, and private bundle publication."""

from __future__ import annotations

import os
import secrets
import stat
from datetime import datetime, timezone
from pathlib import Path

from socratic_learn import __version__
from socratic_learn.errors import FilesystemError, IntegrityError, SourceError
from socratic_learn.safe_fs import (
    IdentityMismatchError,
    PathIdentity,
    PostMutationIdentityError,
    TrackedDirectory,
    identity_bound_mkdir,
    publish_tracked_directory,
    remove_tracked_tree,
    require_trusted_regular_file,
    status_identity,
    track_directory,
)
from socratic_learn.safe_fs import _is_reparse_or_symlink
from socratic_learn.sources.bundle import build_bundle_tree, validate_source_bundle
from socratic_learn.sources.html import extract_html
from socratic_learn.sources.http import MAX_RAW_BYTES, fetch_url
from socratic_learn.sources.ids import source_id_for_local, source_id_for_url
from socratic_learn.sources.model import IngestedSource, SourceRequest
from socratic_learn.sources.pdf import extract_pdf

_MEDIA_PDF = frozenset({"application/pdf"})
_MEDIA_HTML = frozenset({"text/html", "application/xhtml+xml"})


def ingest_source(records: Path, request: SourceRequest) -> IngestedSource:
    records_root = records.resolve()
    sources_root = records_root / "sources"
    staging: TrackedDirectory | None = None
    try:
        if request.kind == "local_pdf":
            raw, document, source_id, display_origin = _ingest_local_pdf(request, records_root)
        elif request.kind == "url":
            raw, document, source_id, display_origin = _ingest_url(request)
        else:
            raise SourceError(
                "unsupported source kind",
                remediation="Use a URL or local PDF source.",
            )

        destination = sources_root / source_id
        if not sources_root.exists():
            identity_bound_mkdir(sources_root, root=records_root)

        staging_dir = sources_root / f".staging-{secrets.token_hex(8)}"
        staging = identity_bound_mkdir(staging_dir, root=records_root)
        extracted_at = datetime.now(timezone.utc)
        metadata = build_bundle_tree(
            staging.path,
            raw=raw,
            document=document,
            source_id=source_id,
            display_origin=display_origin,
            extracted_at=extracted_at,
        )
        validate_source_bundle(staging.path, source_id)
        staging = track_directory(staging.path)

        def _validate_existing(path: Path) -> bool:
            try:
                validate_source_bundle(path, source_id)
            except IntegrityError:
                return False
            return True

        destination_existed = destination.exists()
        try:
            published = publish_tracked_directory(
                staging,
                destination,
                root=records_root,
                validate_existing=_validate_existing,
            )
        except PostMutationIdentityError as error:
            raise IntegrityError(
                str(error),
                remediation="preserve the bundle tree and retry ingestion",
            ) from error
        except IdentityMismatchError as error:
            _cleanup_staging(staging)
            staging = None
            raise IntegrityError(
                str(error),
                remediation="preserve the bundle tree and retry ingestion",
            ) from error
        except OSError as error:
            _cleanup_staging(staging)
            staging = None
            raise FilesystemError(
                "source bundle publication failed",
                remediation="check disk space and permissions, then retry",
            ) from error
        staging = None

        metadata = validate_source_bundle(published, source_id)
        return IngestedSource(
            bundle_path=published,
            source_id=source_id,
            metadata=metadata,
            reused=destination_existed,
        )
    except (SourceError, IntegrityError, FilesystemError):
        raise
    except IdentityMismatchError as error:
        raise IntegrityError(
            str(error),
            remediation="preserve the bundle tree and retry ingestion",
        ) from error
    except Exception as error:
        if staging is not None:
            _cleanup_staging(staging)
        raise FilesystemError(
            "source bundle publication failed",
            remediation="check disk space and permissions, then retry",
        ) from error


def _cleanup_staging(staging: TrackedDirectory) -> None:
    try:
        remove_tracked_tree(staging)
    except IdentityMismatchError as error:
        raise IntegrityError(
            str(error),
            remediation="preserve the staging tree and retry ingestion",
        ) from error


def _lexical_absolute_path(origin: str) -> Path:
    path = Path(origin)
    if not path.is_absolute():
        return path.absolute()
    return path


def _ingest_local_pdf(request: SourceRequest, records_root: Path) -> tuple[bytes, object, str, str]:
    path = _lexical_absolute_path(request.origin)
    trusted_root = Path(path.anchor)
    try:
        file_identity = require_trusted_regular_file(path, root=trusted_root)
    except IdentityMismatchError as error:
        raise SourceError(
            "local PDF is not a regular file",
            remediation="Provide a readable local PDF file, not a link or directory.",
        ) from error
    try:
        raw = _read_bounded_local_file(path, file_identity)
    except SourceError:
        raise
    except OSError as error:
        raise FilesystemError(
            "local PDF could not be read",
            remediation="Check file permissions and retry.",
        ) from error
    filename = path.name
    if not filename:
        raise SourceError(
            "local PDF filename is missing",
            remediation="Provide a PDF file with a filename.",
        )
    display_origin = filename
    try:
        document = extract_pdf(raw, title=filename)
    except SourceError:
        raise
    source_id = source_id_for_local(raw)
    return raw, document, source_id, display_origin


def _ingest_url(request: SourceRequest) -> tuple[bytes, object, str, str]:
    try:
        fetched = fetch_url(
            request.origin,
            allow_private_network=request.allow_private_network,
            user_agent=f"Socratic-Learn/{__version__}",
        )
    except SourceError:
        raise
    raw = fetched.raw
    if fetched.media_type in _MEDIA_PDF:
        document = extract_pdf(raw, title=_title_from_display_origin(fetched.display_origin))
    elif fetched.media_type in _MEDIA_HTML:
        document = extract_html(
            raw,
            content_type=fetched.media_type,
            title_hint=fetched.display_origin,
        )
    else:
        raise SourceError(
            "retrieved media type is not supported",
            remediation="Provide HTML or PDF content.",
        )
    source_id = source_id_for_url(fetched.canonical_url, raw)
    return raw, document, source_id, fetched.display_origin


def _title_from_display_origin(display_origin: str) -> str:
    candidate = Path(display_origin.rsplit("://", 1)[-1]).name
    return candidate or display_origin


def _read_bounded_local_file(path: Path, expected_identity: PathIdentity) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        status = os.fstat(descriptor)
        if _is_reparse_or_symlink(status) or not stat.S_ISREG(status.st_mode):
            raise SourceError(
                "local PDF is not a regular file",
                remediation="Provide a readable local PDF file, not a link or directory.",
            )
        if status_identity(status) != expected_identity:
            raise SourceError(
                "local PDF changed before it could be read",
                remediation="Retry with a stable local PDF path.",
            )
        data = bytearray()
        while True:
            block = os.read(descriptor, 65536)
            if not block:
                break
            data.extend(block)
            if len(data) >= MAX_RAW_BYTES + 1:
                raise SourceError(
                    f"source exceeds {MAX_RAW_BYTES} bytes",
                    remediation="Use a smaller PDF or split the material.",
                )
        return bytes(data)
    finally:
        os.close(descriptor)
