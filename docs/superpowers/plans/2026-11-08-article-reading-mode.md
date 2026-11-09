# Article Reading Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `socratic read` for safe URL/local-PDF ingestion and source-grounded Socratic learning across Pi, Claude Code, and Antigravity.

**Architecture:** Extend the existing launcher with an optional immutable `SourceRequest`. A new `socratic_learn.sources` package converts supported inputs into atomically published private bundles, then a shared payload builder supplies the same source contract through host-specific argument envelopes. The canonical protocol gains source-study rules, and the semantic evaluator reuses the production ingestion and bootstrap builders through versioned suites.

**Tech Stack:** Python 3.11+, standard-library networking/HTML parsing, `pypdf>=7.0,<8`, `unittest`, Hatchling, PyInstaller, existing identity-bound filesystem helpers, existing Antigravity semantic evaluator.

## Global Constraints

- Preserve normal-session host arguments byte-for-byte when `source is None`.
- `socratic read` is console-only; `python -m socratic_learn` remains administrative.
- Accept HTTP/HTTPS HTML or PDF and local regular PDF files only.
- Raw input limit: 20 MiB; PDF limit: 500 pages; normalized text limit: 5,000,000 code points; chunk limit: 12,000 code points.
- Reject URL credentials and blocked network destinations at every redirect unless one-command `--allow-private-network` is set.
- Keep source bundles private under `<records>/sources/<source-id>/`; never commit real learner sources.
- Treat source content as untrusted study material, not instructions; document this as best-effort rather than a sandbox.
- Source study remains externally unverified unless the learner explicitly requests host-provided research.
- Use TDD for every behavior change: failing test, observed failure, minimal implementation, passing focused tests, then broader verification.
- Generated `dist/` files are changed only through `python -m socratic_learn build`.
- Deliver milestones in order: storage/packaging → ingestion → CLI/protocol → semantic gate.

---

## Milestone 1: Trusted storage and packaging

### Task 1: Declare and package the PDF runtime dependency

**Files:**
- Modify: `pyproject.toml`
- Modify: `socratic-learn.spec`
- Modify: `tests/test_packaging.py`
- Modify: `tests/test_universal_smoke.py`
- Modify: `.github/workflows/native-python.yml`
- Modify: `.github/workflows/release.yml`
- Modify: `README.md`
- Modify: `tests/validate_repository.py`
- Modify: `tests/test_validate_repository.py`
- Create: `tests/pdf_fixture.py`
- Create: `tests/fixtures/sources/minimal-text.pdf`

**Interfaces:**
- Produces: declared runtime dependency `pypdf>=7.0,<8`.
- Produces: `tests.pdf_fixture.build_text_pdf(pages: tuple[str, ...]) -> bytes`.
- Preserves: published wheel excludes `evaluation/` and private source data.

- [ ] **Step 1: Add failing packaging assertions**

Add tests that require the dependency and dependency-aware installation:

```python
# tests/test_packaging.py
import tomllib

def test_runtime_declares_supported_pypdf_major(self) -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text("utf-8"))
    self.assertIn("pypdf>=7.0,<8", project["project"]["dependencies"])

def test_native_spec_collects_pypdf(self) -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "socratic-learn.spec").read_text("utf-8")
    self.assertIn('collect_submodules("pypdf")', text)
```

Update the installed-console test to run:

```python
dependency = subprocess.run(
    [str(python), "-c", "import pypdf; print(pypdf.__version__)"],
    capture_output=True,
    text=True,
    check=False,
)
self.assertEqual(0, dependency.returncode, dependency.stderr)
```

- [ ] **Step 2: Run packaging tests and verify RED**

Run:

```powershell
python -m unittest tests.test_packaging -v
```

Expected: dependency and PyInstaller assertions fail because `pypdf` is absent.

- [ ] **Step 3: Add deterministic textual-PDF fixture generation**

Create `tests/pdf_fixture.py` with a deterministic minimal PDF writer. It must:

```python
from __future__ import annotations

def build_text_pdf(pages: tuple[str, ...]) -> bytes:
    """Return a deterministic, uncompressed PDF containing Helvetica text."""
    if not pages:
        raise ValueError("at least one page is required")
    encoded_pages = tuple(page.encode("ascii") for page in pages)
    page_ids = tuple(4 + index * 2 for index in range(len(pages)))
    content_ids = tuple(page_id + 1 for page_id in page_ids)
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Count {len(pages)} /Kids [{kids}] >>".encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for page_id, content_id, page in zip(page_ids, content_ids, encoded_pages):
        lines = page.splitlines() or [b""]
        escaped = [
            line.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
            for line in lines
        ]
        text = b" Tj T* ".join(b"(" + line + b")" for line in escaped) + b" Tj"
        stream = b"BT /F1 12 Tf 14 TL 72 720 Td " + text + b" ET"
        objects.extend(
            (
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 3 0 R >> >> "
                    f"/Contents {content_id} 0 R >>"
                ).encode("ascii"),
                b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
                + stream
                + b"\nendstream",
            )
        )
    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{object_id} 0 obj\n".encode("ascii"))
        document.extend(body)
        document.extend(b"\nendobj\n")
    xref = len(document)
    document.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    document.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        document.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    document.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(document)
```

Generate `tests/fixtures/sources/minimal-text.pdf` with two paragraphs and
assert:

```python
from pypdf import PdfReader

reader = PdfReader("tests/fixtures/sources/minimal-text.pdf")
self.assertIn("Evidence", reader.pages[0].extract_text())
```

- [ ] **Step 4: Implement dependency-aware packaging**

Change:

```toml
dependencies = [
  "pypdf>=7.0,<8",
]
```

Change PyInstaller collection to:

```python
hiddenimports = (
    collect_submodules("socratic_learn")
    + collect_submodules("learning_tutor")
    + collect_submodules("pypdf")
)
```

Remove `--no-deps` only from installed-wheel smoke paths. Keep build isolation
and all private-package exclusions unchanged.

- [ ] **Step 5: Update workflow and validator contracts**

Make `.github/workflows/native-python.yml` and `.github/workflows/release.yml`
install wheels with dependencies. Update `tests/validate_repository.py` to
require dependency-aware installation and a frozen PDF smoke command rather
than a standard-library-only statement. Change README engineering evidence
from “standard-library Python” to “dependency-light Python with pypdf for
textual PDF extraction.”

- [ ] **Step 6: Run focused packaging verification**

Run:

```powershell
python -m unittest tests.test_packaging tests.test_universal_smoke tests.test_validate_repository -v
python tests/validate_repository.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add pyproject.toml socratic-learn.spec README.md .github tests
git commit -m "build: package PDF extraction runtime"
```

---

### Task 2: Add trusted private-tree publication

**Files:**
- Modify: `socratic_learn/safe_fs.py`
- Modify: `tests/test_safe_fs.py`
- Create: `tests/test_source_bundle_fs.py`

**Interfaces:**
- Consumes: `TrackedDirectory`, `identity_bound_mkdir`, `identity_bound_replace`, `remove_tracked_tree`, `capture_parent_chain`.
- Produces: `publish_tracked_directory(staging: TrackedDirectory, destination: Path, *, root: Path, validate_existing: Callable[[Path], bool]) -> Path`.
- Produces: `require_trusted_regular_file(path: Path, *, root: Path) -> PathIdentity`.

- [ ] **Step 1: Write failing ancestor, collision, cleanup, and reuse tests**

Add these exact test methods:

- `test_publish_rejects_linked_destination_ancestor`: create a trusted root, a
  real external directory, and `root/sources` as a link to that directory;
  assert `IdentityMismatchError` and no external child creation.
- `test_publish_reuses_valid_existing_bundle`: create tracked staging and a
  valid existing destination; pass `lambda path: path == destination`; assert
  the destination is returned and staging is removed.
- `test_publish_rejects_invalid_existing_bundle`: pass a validator returning
  `False`; assert `IdentityMismatchError`, unchanged destination bytes, and
  preserved staging.
- `test_publish_removes_owned_staging_after_pre_publish_failure`: inject a
  failure before rename; assert exact tracked staging cleanup.
- `test_publish_preserves_ambiguous_tree_after_identity_change`: replace one
  staged entry in the race hook; assert `IdentityMismatchError` and preserved
  recovery tree.

On Windows, create a junction/reparse fixture when capability exists; otherwise
skip only that capability-specific assertion with the existing platform
pattern.

- [ ] **Step 2: Run filesystem tests and verify RED**

Run:

```powershell
python -m unittest tests.test_safe_fs tests.test_source_bundle_fs -v
```

Expected: import failure for the new publication helpers.

- [ ] **Step 3: Implement trusted regular-file validation**

Add `require_trusted_regular_file` using `capture_parent_chain`,
`follow_symlinks=False`, `_is_reparse_or_symlink`, and identity verification.
It must reject paths outside `root`, linked/reparse ancestors, non-regular
leaves, and leaf identity changes.

- [ ] **Step 4: Implement atomic no-replace directory publication**

`publish_tracked_directory` must:

1. verify `staging` is a tracked plain directory under `root`;
2. capture source and destination parent chains;
3. if destination exists, call `validate_existing`;
4. remove only the operation-owned staging tree when existing validation
   succeeds;
5. reject an invalid existing destination without mutating it;
6. otherwise call `identity_bound_replace(staging.path, destination,
   root=root, expected_source=staging.identity,
   expected_source_chain=source_chain,
   expected_destination_chain=destination_chain)`;
7. return the validated destination path;
8. preserve ambiguous trees on `PostMutationIdentityError`.

- [ ] **Step 5: Run focused and full safe-filesystem tests**

Run:

```powershell
python -m unittest tests.test_safe_fs tests.test_source_bundle_fs -v
```

Expected: PASS, with only capability-aware platform skips.

- [ ] **Step 6: Commit**

```powershell
git add socratic_learn/safe_fs.py tests/test_safe_fs.py tests/test_source_bundle_fs.py
git commit -m "feat(storage): publish private source trees safely"
```

---

## Milestone 2: Deterministic source ingestion

### Task 3: Define source models, errors, identities, and normalization

**Files:**
- Modify: `socratic_learn/errors.py`
- Create: `socratic_learn/sources/__init__.py`
- Create: `socratic_learn/sources/model.py`
- Create: `socratic_learn/sources/ids.py`
- Create: `socratic_learn/sources/normalize.py`
- Create: `tests/test_sources_model.py`
- Create: `tests/test_sources_normalize.py`

**Interfaces:**
- Produces: `SourceError(exit_code = 6)`.
- Produces: `SourceRequest`, `FetchedBytes`, `ExtractedSection`, `ExtractedDocument`, `BundleMetadata`, `IngestedSource`.
- Produces: `source_id_for_local(raw: bytes) -> str`.
- Produces: `source_id_for_url(canonical_url: str, raw: bytes) -> str`.
- Produces: `normalize_text(text: str) -> str`.
- Produces: `chunk_section(text: str, *, limit: int = 12_000) -> tuple[str, ...]`.

- [ ] **Step 1: Write failing exact-model and normalization tests**

Use these contracts:

```python
SourceKind = Literal["url", "local_pdf"]

@dataclass(frozen=True)
class SourceRequest:
    origin: str
    kind: SourceKind
    allow_private_network: bool = False

@dataclass(frozen=True)
class ExtractedSection:
    label: str
    text: str

@dataclass(frozen=True)
class ExtractedDocument:
    title: str
    media_type: str
    sections: tuple[ExtractedSection, ...]
```

Assert NFC normalization, LF line endings, whitespace preservation between
paragraphs, 12,000-code-point maximum, stable local IDs independent of path,
and query-sensitive URL IDs.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
python -m unittest tests.test_sources_model tests.test_sources_normalize -v
```

Expected: modules do not exist.

- [ ] **Step 3: Implement models and stable IDs**

Use:

```python
def source_id_for_local(raw: bytes) -> str:
    return hashlib.sha256(b"local-pdf\0" + raw).hexdigest()

def source_id_for_url(canonical_url: str, raw: bytes) -> str:
    payload = b"url\0" + canonical_url.encode("utf-8") + b"\0" + raw
    return hashlib.sha256(payload).hexdigest()
```

`SourceError` is a direct `LearningTutorError` subclass with `exit_code = 6`.

- [ ] **Step 4: Implement deterministic normalization and chunking**

Use `unicodedata.normalize("NFC", text)`, normalize CRLF/CR to LF, collapse
horizontal whitespace inside lines, trim repeated blank lines to one, and split
at paragraph/Unicode-whitespace boundaries without exceeding 12,000 code
points. Raise `SourceError` above 5,000,000 normalized code points or below 200
non-whitespace code points.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m unittest tests.test_sources_model tests.test_sources_normalize -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add socratic_learn/errors.py socratic_learn/sources tests/test_sources_model.py tests/test_sources_normalize.py
git commit -m "feat(sources): define source contracts"
```

---

### Task 4: Extract textual PDF and deterministic HTML

**Files:**
- Create: `socratic_learn/sources/pdf.py`
- Create: `socratic_learn/sources/html.py`
- Create: `tests/test_sources_pdf.py`
- Create: `tests/test_sources_html.py`
- Create: `tests/fixtures/sources/article.html`
- Create: `tests/fixtures/sources/image-only.pdf`
- Create: `tests/fixtures/sources/encrypted.pdf`

**Interfaces:**
- Produces: `extract_pdf(raw: bytes, *, title: str) -> ExtractedDocument`.
- Produces: `extract_html(raw: bytes, *, content_type: str | None, title_hint: str) -> ExtractedDocument`.

- [ ] **Step 1: Write failing PDF extraction tests**

Test textual pages, `%PDF-` within first 1,024 bytes, malformed PDF,
encryption, 501 pages, image-only/under-200-character content, and page labels:

```python
document = extract_pdf(raw, title="paper.pdf")
self.assertEqual("application/pdf", document.media_type)
self.assertEqual(("Page 1", "Page 2"), tuple(s.label for s in document.sections))
self.assertIn("Evidence", document.sections[0].text)
```

- [ ] **Step 2: Write failing HTML extraction tests**

Test `article > main > body` precedence, excluded elements, headings,
paragraphs, block quotes, lists, charset precedence, no JavaScript execution,
and under-200-character rejection.

- [ ] **Step 3: Run extractor tests and verify RED**

Run:

```powershell
python -m unittest tests.test_sources_pdf tests.test_sources_html -v
```

Expected: extractor modules do not exist.

- [ ] **Step 4: Implement PDF extraction**

Use `PdfReader(BytesIO(raw), strict=False)`. Reject encrypted documents unless
`reader.decrypt("")` succeeds without credentials. Reject more than 500 pages.
Extract each page once, normalize text through Task 3, label pages `Page N`,
and apply the document-wide 200-non-whitespace threshold.

- [ ] **Step 5: Implement HTML extraction**

Create an `HTMLParser` subclass that records candidate buffers for `article`,
`main`, and `body`, ignores excluded subtrees, emits block boundaries for
`h1`–`h6`, `p`, `blockquote`, and `li`, and captures `<title>`. Decode in this
order: valid HTTP charset, BOM, valid `<meta charset>` in first 4,096 bytes,
UTF-8 with replacement. Pick the first non-empty candidate by precedence.

- [ ] **Step 6: Run extractor tests**

Run:

```powershell
python -m unittest tests.test_sources_pdf tests.test_sources_html -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add socratic_learn/sources/pdf.py socratic_learn/sources/html.py tests/test_sources_pdf.py tests/test_sources_html.py tests/fixtures/sources
git commit -m "feat(sources): extract PDF and HTML text"
```

---

### Task 5: Add bounded URL transport

**Files:**
- Create: `socratic_learn/sources/http.py`
- Create: `tests/test_sources_http.py`

**Interfaces:**
- Produces: `canonicalize_url(url: str) -> tuple[str, str]` returning retrieval and redacted display URLs.
- Produces: `fetch_url(url: str, *, allow_private_network: bool, user_agent: str) -> FetchedBytes`.
- Produces constants `MAX_RAW_BYTES = 20 * 1024 * 1024`, `SOCKET_TIMEOUT_SECONDS = 20`, `MAX_REDIRECTS = 5`.

- [ ] **Step 1: Write failing URL policy tests**

Use an in-process `ThreadingHTTPServer` and injected resolver/connection seams.
Cover HTTP/HTTPS only, credential rejection, query redaction, five redirects,
public-to-private redirect rejection, blocked IPv4/IPv6 classes, private
opt-in, peer-address recheck, proxy disabling, `Accept-Encoding: identity`,
content-encoding rejection, 20,971,521-byte rejection, and sanitized errors.

- [ ] **Step 2: Run HTTP tests and verify RED**

Run:

```powershell
python -m unittest tests.test_sources_http -v
```

Expected: module does not exist.

- [ ] **Step 3: Implement canonicalization and address policy**

Normalize scheme/IDNA host/default port/path percent encoding, strip fragment,
reject user information, retain query only in the in-memory retrieval URL, and
construct display URL without query. Classify every `ipaddress.ip_address`
result; reject private, loopback, link-local, multicast, unspecified, or
reserved unless opted in.

- [ ] **Step 4: Implement redirect-controlled transport**

Use `http.client.HTTPConnection`/`HTTPSConnection` directly so the connected
socket peer can be checked before request headers are sent. Resolve every hop,
disable proxy environment use by not using `urllib` openers, preserve TLS
verification and SNI for HTTPS, send only fixed safe headers, count redirects,
stream into a `bytearray`, and stop before byte 20,971,521.

- [ ] **Step 5: Implement media classification**

Accept HTML/XHTML/PDF content types. For missing/octet-stream, inspect first
1,024 bytes for `%PDF-`, `<html`, or `<!doctype html` case-insensitively.
Reject non-identity content encoding. Return `FetchedBytes` with raw bytes,
canonical retrieval URL kept only in memory, redacted display origin, and
normalized media type.

- [ ] **Step 6: Run HTTP tests**

Run:

```powershell
python -m unittest tests.test_sources_http -v
```

Expected: PASS without public-network access.

- [ ] **Step 7: Commit**

```powershell
git add socratic_learn/sources/http.py tests/test_sources_http.py
git commit -m "feat(sources): fetch bounded article URLs"
```

---

### Task 6: Publish and reuse complete source bundles

**Files:**
- Create: `socratic_learn/sources/bundle.py`
- Create: `socratic_learn/sources/ingest.py`
- Modify: `socratic_learn/sources/__init__.py`
- Create: `tests/test_sources_bundle.py`
- Create: `tests/test_sources_ingest.py`

**Interfaces:**
- Produces: `ingest_source(records: Path, request: SourceRequest) -> IngestedSource`.
- Produces: `validate_source_bundle(path: Path, expected_id: str) -> BundleMetadata`.
- Consumes: Task 2 safe publication; Tasks 3–5 models/extractors/transport.

- [ ] **Step 1: Write failing bundle-layout and end-to-end tests**

Assert exact bundle tree, lowercase 64-hex ID, UTF-8/LF/NFC chunks, maximum
chunk size, metadata with no query/absolute local path, page/heading index,
atomic cleanup, valid reuse without rewriting mtimes, invalid existing bundle
rejection, and URL/local end-to-end ingestion.

- [ ] **Step 2: Run bundle tests and verify RED**

Run:

```powershell
python -m unittest tests.test_sources_bundle tests.test_sources_ingest -v
```

Expected: bundle/ingest modules do not exist.

- [ ] **Step 3: Implement deterministic bundle serialization**

Write `metadata.json` with canonical sorted JSON, `index.md` with stable section
ordering, `original.bin`, and `sections/NNNN.txt`. Split each extracted section
with `chunk_section`; index labels include heading/page plus chunk sequence.
Never serialize retrieval URL query or local directory.

- [ ] **Step 4: Implement ingestion orchestration**

For local PDF, use `require_trusted_regular_file`, enforce 20 MiB while reading,
extract PDF, and derive local ID. For URL, call `fetch_url`, dispatch by media
type, and derive URL ID. Stage under `records/sources/.staging-<random>`, track
the completed tree, and publish with Task 2. Map extraction/network failures to
`SourceError`, managed-tree mismatches to `IntegrityError`, and writes to
`FilesystemError`.

- [ ] **Step 5: Run all source tests**

Run:

```powershell
python -m unittest discover -s tests -p "test_sources*.py" -v
python -m unittest tests.test_source_bundle_fs -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add socratic_learn/sources tests/test_sources_bundle.py tests/test_sources_ingest.py
git commit -m "feat(sources): publish indexed source bundles"
```

---

## Milestone 3: CLI, hosts, and protocol

### Task 7: Build shared source payloads and host envelopes

**Files:**
- Create: `socratic_learn/sources/payload.py`
- Modify: `socratic_learn/hosts.py`
- Modify: `tests/test_hosts.py`
- Create: `tests/test_sources_payload.py`
- Modify: `docs/launcher-adapters.md`

**Interfaces:**
- Produces: `build_source_study_payload(*, learner_goal: str, index_path: Path, metadata_path: Path) -> str`.
- Extends: `command_for(adapter, executable, protocol, goal, source_study_payload=None) -> tuple[str, ...]`.
- Preserves: current argv exactly when payload is `None`.

- [ ] **Step 1: Write failing exact-payload and argv tests**

Assert exact multiline payload text from the spec. Assert Pi/Claude final
argument equals payload and Antigravity argument equals normal protocol prefix
plus `\n\n--- SOCRATIC LEARN SOURCE STUDY ---\n` plus payload. Retain every
existing normal-host equality assertion.

- [ ] **Step 2: Run host tests and verify RED**

Run:

```powershell
python -m unittest tests.test_sources_payload tests.test_hosts -v
```

Expected: missing payload builder/argument.

- [ ] **Step 3: Implement pure payload builder**

Build one string from learner goal and absolute index/metadata paths. Reject
blank goals and non-absolute paths with `ValueError`; do not read source files.

- [ ] **Step 4: Extend host adapters without normal regressions**

Add optional payload to adapter call signatures. Pi and Claude use
`payload or goal` as the final prompt. Antigravity uses the existing bootstrap
for `None`; for read mode it emits the protocol instruction, delimiter, and
payload exactly once.

- [ ] **Step 5: Update adapter documentation and run tests**

Run:

```powershell
python -m unittest tests.test_sources_payload tests.test_hosts -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add socratic_learn/sources/payload.py socratic_learn/hosts.py tests/test_sources_payload.py tests/test_hosts.py docs/launcher-adapters.md
git commit -m "feat(hosts): deliver source study payloads"
```

---

### Task 8: Add the read command and launcher lifecycle

**Files:**
- Modify: `socratic_learn/cli.py`
- Modify: `socratic_learn/launcher.py`
- Modify: `tests/test_console_cli.py`
- Modify: `tests/test_launcher.py`
- Create: `tests/test_read_cli.py`
- Create: `tests/test_read_launcher.py`

**Interfaces:**
- Extends: `LaunchOptions(goal: str | None, agent: AgentName | None,
  here: bool, cwd: Path, source: SourceRequest | None = None)`.
- Produces: `parse_read_arguments(arguments: list[str]) -> LaunchOptions`.
- Consumes: `ingest_source`, `build_source_study_payload`, extended `command_for`.

- [ ] **Step 1: Write failing CLI grammar tests**

Cover URL/local PDF, goal words, read options before/after command, `--`,
filename beginning with `-`, `socratic learn read critically`, reserved
`socratic read critically`, console-only behavior, and abbreviation rejection.

- [ ] **Step 2: Write failing lifecycle-order tests**

Record calls and assert:

```python
self.assertEqual(
    ["detect", "goal", "agent", "workspace", "ingest", "spawn"],
    events,
)
```

Also assert missing host performs no prompt/workspace/source access; blank goal
performs no source access; ingestion receives `workspace.records`; source
errors return exit code 6/no traceback; normal `LaunchOptions` produces the
same argv as before.

- [ ] **Step 3: Run CLI/launcher tests and verify RED**

Run:

```powershell
python -m unittest tests.test_read_cli tests.test_read_launcher tests.test_console_cli tests.test_launcher -v
```

Expected: read dispatch and source field are missing.

- [ ] **Step 4: Implement read parsing**

Dispatch read before the free-form goal parser by locating the first non-option
command token while respecting option values and `--`. Parse
`--agent`, `--here`, `--allow-private-network`, source, and remaining goal.
Use `parse_source_origin` to construct `SourceRequest`. Keep
`python -m socratic_learn` unchanged.

- [ ] **Step 5: Implement the exact launcher lifecycle**

Extend `LaunchOptions`; preserve detect/goal/agent behavior; prepare workspace;
ingest only after valid goal and agent; build payload from returned absolute
paths; call `command_for(host.adapter, host.executable, workspace.protocol,
goal, source_study_payload=payload)`; inherit stdio and return child status
exactly as normal sessions do.

- [ ] **Step 6: Run focused launcher tests**

Run:

```powershell
python -m unittest tests.test_read_cli tests.test_read_launcher tests.test_console_cli tests.test_launcher -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add socratic_learn/cli.py socratic_learn/launcher.py tests/test_console_cli.py tests/test_launcher.py tests/test_read_cli.py tests/test_read_launcher.py
git commit -m "feat(cli): add socratic read"
```

---

### Task 9: Upgrade the canonical protocol and conformance contract

**Files:**
- Modify: `core/pedagogy.md`
- Modify: `core/session-protocol.md`
- Modify: `core/evidence-policy.md`
- Modify: `AGENTS.md`
- Modify: `socratic_learn/conformance.py`
- Modify: `socratic_learn/__init__.py`
- Modify: `tests/test_conformance.py`
- Modify: `tests/test_manifest.py`
- Generated: `dist/socratic-learn.prompt.md`
- Generated: `dist/manifest.json`

**Interfaces:**
- Produces: protocol version `1.2.0`.
- Produces conformance diagnostic: `source-study-external-verification-gate`.
- Refines: `volatile-primary-source-verification` source-study carve-out.

- [ ] **Step 1: Add failing conformance tests**

Require source assertion/support/external-verification markers, source-bounded
default, explicit request gate, focused single learner task, source location,
orchestration privacy, nonexistence-evidence caution, and vocabulary readiness.
Delete each required marker from a synthetic bundle and assert the exact
diagnostic code.

- [ ] **Step 2: Run conformance tests and verify RED**

Run:

```powershell
python -m unittest tests.test_conformance tests.test_manifest -v
```

Expected: missing new diagnostic and protocol version.

- [ ] **Step 3: Update canonical documents**

Add the approved source-study behavior without exposing protocol labels to the
learner. Strengthen one-focused-task language to prohibit claim × dimension
batches. Add the explicit external-research gate and preserve normal
autonomous verification outside source-study mode.

- [ ] **Step 4: Add conformance contract and bump version**

Set `PROTOCOL_VERSION = "1.2.0"`. Add marker groups for the new gate and update
required diagnostic codes. Keep the existing volatile contract, but require
the evidence policy to state its source-study exception.

- [ ] **Step 5: Regenerate distribution**

Run:

```powershell
python -m socratic_learn build
```

Expected: `dist/manifest.json` and `dist/socratic-learn.prompt.md` update
deterministically.

- [ ] **Step 6: Run protocol verification**

Run:

```powershell
python -m unittest tests.test_conformance tests.test_manifest tests.test_build tests.test_install -v
python tests/validate_repository.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add AGENTS.md core socratic_learn/conformance.py socratic_learn/__init__.py tests/test_conformance.py tests/test_manifest.py dist
git commit -m "feat(protocol): add source-grounded study mode"
```

---

### Task 10: Document and smoke-test the installed read workflow

**Files:**
- Modify: `README.md`
- Modify: `tests/test_packaging.py`
- Modify: `tests/test_universal_smoke.py`
- Modify: `.github/workflows/native-python.yml`
- Modify: `.github/workflows/release.yml`
- Modify: `tests/validate_repository.py`
- Modify: `tests/test_validate_repository.py`

**Interfaces:**
- Consumes: installed/frozen `socratic read`.
- Produces: fake-host receipt proving source payload and bundle access.

- [ ] **Step 1: Add failing installed-wheel and frozen-read smoke assertions**

Create an isolated home and fake host executable that records argv. Run:

```text
socratic read --agent pi tests/fixtures/sources/minimal-text.pdf explain its evidence
```

Assert exit 0, receipt contains source payload/index path, index exists during
host execution, and no source bundle appears in the repository or package.
Repeat adapter argv contracts for fake Claude and Antigravity.

- [ ] **Step 2: Run smoke tests and verify RED**

Run:

```powershell
python -m unittest tests.test_packaging tests.test_universal_smoke -v
```

Expected: installed/frozen read smoke is absent or fails.

- [ ] **Step 3: Add README guidance and limitations**

Document URL/PDF examples, limits, private bundle location, no OCR/JavaScript,
source-grounded versus externally verified claims, prompt-injection
best-effort, provider/model ownership, and no learning-effectiveness claim.

- [ ] **Step 4: Update workflows and validators**

Require dependency-aware wheel read smoke in native matrix and frozen textual
PDF read smoke in release builds. Extend repository validation to require the
new commands, dependency wording, and source-private exclusions.

- [ ] **Step 5: Run milestone verification**

Run:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python tests/validate_repository.py
python -m socratic_learn build
git diff --exit-code -- dist
```

Expected: all tests pass, validator passes, generated dist is clean.

- [ ] **Step 6: Commit**

```powershell
git add README.md .github tests
git commit -m "docs: ship article reading workflow"
```

---

## Milestone 4: Semantic release gate

### Task 11: Version semantic scenarios, run records, and suites

**Files:**
- Modify: `evaluation/schema.py`
- Modify: `evaluation/session.py`
- Modify: `evaluation/isolation.py`
- Modify: `evaluation/report.py`
- Modify: `evaluation/cli.py`
- Modify: `tests/test_evaluation_schema.py`
- Modify: `tests/test_evaluation_session.py`
- Modify: `tests/test_evaluation_report.py`
- Create: `evaluation/fixtures/suites/baseline-v1.json`
- Create: `evaluation/fixtures/suites/article-reading-v1.json`

**Interfaces:**
- Produces: scenario schema v2 with `source_fixture_id: str | None`.
- Produces: run-record schema v2 with `scenario_sha256`, `rubric_sha256`, `suite_sha256`.
- Produces: `SuiteManifest` and `load_suite_manifest(path: Path) -> SuiteManifest`.
- Preserves: schema-1 read compatibility.

- [ ] **Step 1: Write failing schema-v1 compatibility and v2 identity tests**

Assert existing scenario/run fixtures load unchanged, new v2 fixtures require
exact keys/hashes, duplicate/unknown suite scenarios fail, and every new run
records protocol/scenario/rubric/suite identities.

- [ ] **Step 2: Write failing suite-driven report tests**

Replace assumptions of one hard-coded triplet in new report tests with ordered
suite scenarios. Keep the tracked historical baseline validator test. Assert
wrong suite/rubric/scenario hashes fail.

- [ ] **Step 3: Run evaluation schema/report tests and verify RED**

Run:

```powershell
python -m unittest tests.test_evaluation_schema tests.test_evaluation_session tests.test_evaluation_report -v
```

Expected: v2 fields and suite loader are missing.

- [ ] **Step 4: Implement versioned loaders and immutable manifests**

Keep explicit v1 parsing branches. Add v2 dataclass fields and exact-key
validation. Hash canonical fixture bytes with existing SHA-256 helpers. Add
suite manifests listing scenario IDs, rubric path, report contract, and schema
version.

- [ ] **Step 5: Generalize new report rendering**

Pass `SuiteManifest` into rendering; use its ordered scenario list. Include
suite/rubric/scenario identities in report identity. Preserve historical
baseline parsing and sanitation.

- [ ] **Step 6: Run evaluation schema/report tests**

Run:

```powershell
python -m unittest tests.test_evaluation_schema tests.test_evaluation_session tests.test_evaluation_report -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add evaluation tests/test_evaluation_schema.py tests/test_evaluation_session.py tests/test_evaluation_report.py
git commit -m "feat(evaluation): version semantic suites"
```

---

### Task 12: Add the article scenario and production-bootstrap release gate

**Files:**
- Modify: `evaluation/antigravity.py`
- Modify: `evaluation/isolation.py`
- Modify: `evaluation/session.py`
- Modify: `evaluation/scoring.py`
- Modify: `evaluation/cli.py`
- Modify: `evaluation/fixtures/rubric.json`
- Modify: `tests/test_evaluation_antigravity.py`
- Modify: `tests/test_evaluation_isolation.py`
- Modify: `tests/test_evaluation_session.py`
- Create: `evaluation/fixtures/scenarios/article-reading.json`
- Create: `evaluation/fixtures/sources/article-reading-v1/source.pdf`

**Interfaces:**
- Produces: sourced scenario isolation through production `ingest_source`.
- Produces: production/evaluation bootstrap identity.
- Produces: `article_reading_passes(scorecard: Scorecard, record: RunRecord) -> bool`.
- Adds critical failures `source-claim-presented-as-externally-verified` and `batched-independent-learner-tasks`.

- [ ] **Step 1: Write failing sourced-isolation and bootstrap tests**

Assert the public PDF fixture is copied outside the repository, ingested under
the isolated records root, absolute runtime paths never enter the private run
record, and `evaluation.antigravity.initial_bootstrap` equals production host
construction for the same protocol/goal/source payload.

- [ ] **Step 2: Write failing gate tests**

Build scorecards for:

- 14/16 with required categories at 2, no failure → pass;
- 13/16 → fail;
- required category at 1 → fail;
- any critical failure → fail;
- infrastructure stop → inconclusive/fail release gate;
- non-`observable_outcome` stop → fail.

- [ ] **Step 3: Run semantic-focused tests and verify RED**

Run:

```powershell
python -m unittest tests.test_evaluation_antigravity tests.test_evaluation_isolation tests.test_evaluation_session -v
```

Expected: source fixture/gate/bootstrap support is missing.

- [ ] **Step 4: Add fictitious article fixture and learner scenario**

Generate a short textual PDF with stable headings containing one supported
description, one unsupported causal claim, one vague promotional claim, and
one interest disclosure. Add scenario persona/response policy exactly matching
the design, with `source_fixture_id: "article-reading-v1"` and maximum 15
learner responses.

- [ ] **Step 5: Reuse production ingestion and bootstrap**

During sourced run setup, copy the declared fixture into the external runtime,
call `ingest_source`, build the exact production payload, and call the same host
command builder. Do not duplicate the Antigravity read template in evaluation.
Store fixture IDs and hashes only.

- [ ] **Step 6: Implement the release predicate**

`article_reading_passes` returns true only for `observable_outcome`, no
infrastructure/critical failures, total ≥14, required categories equal 2, and
all others ≥1. CLI/report output labels infrastructure outcomes
“inconclusive,” never “passed.”

- [ ] **Step 7: Run semantic unit verification**

Run:

```powershell
python -m unittest tests.test_evaluation_antigravity tests.test_evaluation_isolation tests.test_evaluation_session tests.test_evaluation_report -v
```

Expected: PASS.

- [ ] **Step 8: Recapture Antigravity runtime contract**

Run the repository's contract-capture command against the installed `agy`
version, review the model/runtime identifiers, and update only:

```text
evaluation/fixtures/antigravity/stream-contract.json
```

Then run:

```powershell
python -m unittest tests.test_evaluation_contract tests.test_evaluation_antigravity -v
```

Expected: PASS with the installed runtime version.

- [ ] **Step 9: Execute and score the live article suite**

Run preflight, article scenario, isolation verification, scoring, and report
through `python -m evaluation.cli` using a new suite ID. Expected release result:
`observable_outcome`, no infrastructure/critical failure, required category
scores of 2, every category ≥1, total ≥14/16. If authentication/quota/network/
runtime/timeout occurs, record it as inconclusive and do not claim release
acceptance.

- [ ] **Step 10: Commit**

```powershell
git add evaluation tests/test_evaluation_antigravity.py tests/test_evaluation_isolation.py tests/test_evaluation_session.py tests/test_evaluation_report.py
git commit -m "test(evaluation): gate article learning semantics"
```

---

## Final verification

- [ ] **Step 1: Run the complete test suite**

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Expected: all available tests pass; only documented capability skips remain.

- [ ] **Step 2: Verify deterministic distribution and repository policy**

```powershell
python -m socratic_learn build
git diff --exit-code -- dist
python tests/validate_repository.py
```

Expected: clean deterministic build and validator PASS.

- [ ] **Step 3: Verify editable and installed console behavior**

```powershell
python -m pip install -e .
socratic --version
socratic --help
```

Expected: version/help succeed and list `read`.

- [ ] **Step 4: Run local read smoke**

```powershell
socratic read --agent antigravity tests/fixtures/sources/minimal-text.pdf evaluate the main claim and its evidence
```

Expected: host starts, confirms an observable source-learning outcome without
orchestration leakage, and can cite the indexed PDF page.

- [ ] **Step 5: Check repository state**

```powershell
git status --short --branch
git log --oneline --decorate -15
```

Expected: only intended commits; no source bundles, raw semantic streams, local
paths, or learner records are tracked.

