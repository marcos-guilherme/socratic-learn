"""Deterministic HTML text extraction without script execution."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from socratic_learn.errors import SourceError
from socratic_learn.sources.model import ExtractedDocument, ExtractedSection
from socratic_learn.sources.normalize import MIN_NON_WHITESPACE_CODE_POINTS, normalize_text

_MEDIA_TYPE = "text/html"
_CANDIDATE_TAGS = ("article", "main", "body")
_EXCLUDED_TAGS = frozenset(
    {"script", "style", "noscript", "svg", "nav", "header", "footer", "form", "aside"}
)
_BLOCK_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote", "li"})
_HEAD_SCAN_BYTES = 4096

_CHARSET_PARAM_RE = re.compile(r"charset\s*=\s*['\"]?([a-zA-Z0-9._-]+)", re.IGNORECASE)
_META_CHARSET_RE = re.compile(
    rb"<meta[^>]+charset\s*=\s*['\"]?([a-zA-Z0-9._-]+)",
    re.IGNORECASE,
)
_META_HTTP_CHARSET_RE = re.compile(
    rb"<meta[^>]+http-equiv\s*=\s*['\"]?content-type['\"]?[^>]+"
    rb"content\s*=\s*['\"][^'\"]*charset\s*=\s*([a-zA-Z0-9._-]+)",
    re.IGNORECASE,
)


def extract_html(raw: bytes, *, content_type: str | None, title_hint: str) -> ExtractedDocument:
    """Extract reading-order text from static HTML."""
    html = _decode_html(raw, content_type)
    parser = _HtmlTextExtractor()
    parser.feed(html)
    parser.close()

    selected = _select_candidate(parser.candidate_blocks)
    if selected is None:
        raise SourceError(
            f"HTML has fewer than {MIN_NON_WHITESPACE_CODE_POINTS} extractable characters; "
            "client-rendered pages are not supported",
            remediation="Save or export static HTML, or provide a PDF.",
        )

    try:
        normalized = normalize_text(selected, require_meaningful=True)
    except SourceError as error:
        if "fewer than" in str(error):
            raise SourceError(
                f"HTML has fewer than {MIN_NON_WHITESPACE_CODE_POINTS} extractable characters; "
                "client-rendered pages are not supported",
                remediation="Save or export static HTML, or provide a PDF.",
            ) from None
        raise

    title = _choose_title(parser.title, title_hint)
    return ExtractedDocument(
        title=title,
        media_type=_MEDIA_TYPE,
        sections=(ExtractedSection(label=title, text=normalized),),
    )


def _decode_html(raw: bytes, content_type: str | None) -> str:
    charset = _http_charset(content_type)
    if charset is not None:
        decoded = _try_decode(raw, charset)
        if decoded is not None:
            return decoded

    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")

    for pattern in (_META_CHARSET_RE, _META_HTTP_CHARSET_RE):
        match = pattern.search(raw[:_HEAD_SCAN_BYTES])
        if match is not None:
            label = match.group(1).decode("ascii", errors="ignore")
            decoded = _try_decode(raw, label)
            if decoded is not None:
                return decoded

    return raw.decode("utf-8", errors="replace")


def _http_charset(content_type: str | None) -> str | None:
    if not content_type:
        return None
    match = _CHARSET_PARAM_RE.search(content_type)
    if match is None:
        return None
    return match.group(1).strip()


def _try_decode(raw: bytes, charset: str) -> str | None:
    normalized = charset.strip().lower().replace("-", "").replace("_", "")
    aliases = {
        "utf8": "utf-8",
        "iso88591": "iso-8859-1",
        "latin1": "iso-8859-1",
    }
    codec = aliases.get(normalized, charset)
    try:
        return raw.decode(codec)
    except (LookupError, UnicodeDecodeError):
        return None


def _select_candidate(candidate_blocks: dict[str, list[str]]) -> str | None:
    for tag in _CANDIDATE_TAGS:
        blocks = candidate_blocks.get(tag, [])
        joined = "\n\n".join(block for block in blocks if block.strip())
        if not joined.strip():
            continue
        non_whitespace = sum(1 for character in joined if not character.isspace())
        if non_whitespace >= MIN_NON_WHITESPACE_CODE_POINTS:
            return joined
    return None


def _choose_title(title: str | None, title_hint: str) -> str:
    if title and _is_meaningful_title(title):
        return normalize_text(title, require_meaningful=False)
    return title_hint


def _is_meaningful_title(title: str) -> bool:
    collapsed = "".join(character for character in title if not character.isspace())
    return len(collapsed) >= 3


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.candidate_blocks: dict[str, list[str]] = {tag: [] for tag in _CANDIDATE_TAGS}
        self.title: str | None = None
        self._exclude_depth = 0
        self._candidate_depth = {tag: 0 for tag in _CANDIDATE_TAGS}
        self._open_blocks: dict[str, list[str]] = {tag: [] for tag in _CANDIDATE_TAGS}
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        if lowered in _EXCLUDED_TAGS:
            self._exclude_depth += 1
            return
        if self._exclude_depth:
            return
        if lowered == "title":
            self._in_title = True
            self._title_parts = []
            return
        if lowered in _CANDIDATE_TAGS:
            self._candidate_depth[lowered] += 1
            self._commit_open_blocks()
        if lowered in _BLOCK_TAGS:
            self._commit_open_blocks()
            for target in self._capture_targets():
                self._open_blocks[target] = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in _EXCLUDED_TAGS and self._exclude_depth:
            self._exclude_depth -= 1
            return
        if self._exclude_depth:
            return
        if lowered == "title" and self._in_title:
            self.title = "".join(self._title_parts).strip()
            self._in_title = False
            return
        if lowered in _BLOCK_TAGS:
            self._commit_open_blocks()
        if lowered in _CANDIDATE_TAGS and self._candidate_depth[lowered] > 0:
            self._commit_open_blocks()
            self._candidate_depth[lowered] -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
            return
        if self._exclude_depth:
            return
        for target in self._capture_targets():
            if not self._open_blocks[target]:
                self._open_blocks[target] = [""]
            self._open_blocks[target][-1] += data

    def close(self) -> None:
        self._commit_open_blocks()
        super().close()

    def _capture_targets(self) -> tuple[str, ...]:
        if self._candidate_depth["article"] > 0:
            return ("article",)
        if self._candidate_depth["main"] > 0:
            return ("main",)
        if self._candidate_depth["body"] > 0:
            return ("body",)
        return ()

    def _commit_open_blocks(self) -> None:
        for target in self._capture_targets():
            parts = self._open_blocks[target]
            if not parts:
                continue
            text = normalize_text("".join(parts), require_meaningful=False)
            if text:
                self.candidate_blocks[target].append(text)
            self._open_blocks[target] = []
