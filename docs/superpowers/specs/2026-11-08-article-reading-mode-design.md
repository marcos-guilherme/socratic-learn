# Article Reading Mode Design

**Date:** 2026-11-08  
**Status:** Approved for implementation planning

## Purpose

Add a first-class article-reading workflow that a learner can start with one
obvious command:

```text
socratic read <URL-or-PDF> [learning goal]
```

The workflow must make the same normalized source available to Pi, Claude Code,
and Antigravity, then apply the existing Socratic Learn protocol to critical
reading. It must distinguish what a source says from what it supports and from
what has been externally verified.

This first release does not perform automatic literature verification. It
prepares the source reliably, improves the protocol behavior exposed by the
semantic test, and records external claims as unverified.

## Product direction

Socratic Learn serves two connected outcomes:

- **learning:** reconstruct, practice, and apply an idea with observable
  evidence;
- **research:** formulate a question, inspect and compare sources, evaluate
  evidence, preserve citations, and produce a traceable synthesis.

Article reading is the shared source foundation, not the complete research
product. This release builds trustworthy ingestion and source-grounded
reasoning. A later `socratic research` design will add canonical search,
multi-source comparison, literature connectors, a claim ledger, and citation
export. Those later features must reuse the source bundles and epistemic
distinctions defined here rather than creating a second ingestion path.

## User experience

### Commands

The new command is:

```text
socratic read SOURCE [GOAL...]
```

Examples:

```text
socratic read https://example.org/article
socratic read paper.pdf understand the argument and test its evidence
socratic read --agent antigravity paper.pdf
socratic read --here paper.pdf compare the method with my notes
socratic read --allow-private-network http://localhost:8000/article
```

`SOURCE` accepts:

- an `http://` or `https://` URL whose response is HTML or PDF;
- a local regular PDF file.

The command rejects unsupported URL schemes, directories, symbolic links,
non-PDF local files, missing files, URLs containing user information, and
public URLs that resolve or redirect to loopback, link-local, private, or
reserved network addresses. `--allow-private-network` is an explicit opt-in
that permits those network destinations for the one supplied read command; it
does not persist as a preference.

If `GOAL` is absent, the launcher asks:

```text
What do you want to be able to do with this source?
```

An empty answer is rejected. The launcher never invents a learning objective
from the source title.

The normal learning command shape remains available:

```text
socratic [--agent AGENT] [--here] [learn] GOAL...
```

The token `read` is reserved as a subcommand only when it is the command name.
A learner who wants to study reading as a subject can use:

```text
socratic learn read critically
```

### Learner-facing behavior

The tutor confirms an observable outcome before diagnosis. During source study,
it:

1. refers to claims by a stable section, page, or excerpt location;
2. distinguishes:
   - what the source states;
   - what support the source itself provides;
   - what remains externally unverified;
3. asks one focused learner task at a time;
4. treats missing support as missing support, not proof that a claim is false;
5. uses hints before complete answers when the learner can make progress;
6. includes source-grounded application or transfer before closure;
7. keeps the session source-bounded unless the learner explicitly asks for
   external verification.

The tutor does not narrate that it is reading prompts, rules, protocols, or
internal files.

If the learner explicitly requests external verification, the host may use its
existing research capabilities under the evidence policy and must cite what it
actually consulted. This is a capability fallback, not a canonical research
feature: this release does not guarantee that every host can search, does not
normalize search results across hosts, and does not label an unchecked claim
as verified.

## Chosen approach

Socratic Learn performs canonical local ingestion instead of delegating source
loading to each host. Host-native loading was rejected because URL support, PDF
support, extraction quality, permissions, and context usage differ across Pi,
Claude Code, and Antigravity. A bare `--source` option was rejected because it
is less discoverable than a dedicated verb and does not communicate a distinct
reading workflow.

The launcher converts every accepted source into a private source bundle. Each
host receives the same source index and chunk files, so host differences begin
after ingestion rather than before it.

## Architecture

### CLI parsing

`socratic_learn.cli` dispatches `read` before the existing free-form goal
parser, in the same way that administrative and self-management commands are
dispatched explicitly today.

The read parser accepts:

- positional `source`;
- positional `goal` with zero or more words;
- `--agent {pi,claude,antigravity}`;
- `--here`;
- `--allow-private-network`.

Argument abbreviation remains disabled. Existing administrative, update, and
uninstall commands retain their current behavior and error codes. Normal
learning keeps its behavior except for the documented reservation of `read` as
a command token.

`read` is recognized only as the first non-option command token. Global read
options are accepted before or after `read`, but parsing stops option
interpretation after `--`. A source filename beginning with `-` therefore
requires `--`. The forms below are equivalent:

```text
socratic --agent pi read article.pdf
socratic read --agent pi article.pdf
```

This reserves a word that was previously valid as the first word of a normal
goal. `socratic read critically` now attempts to open `critically` as a source.
The documented compatibility escape is `socratic learn read critically`.

### Launch request

Replace the launcher-only collection of individual fields with an immutable
request that carries:

- the learner goal or `None`;
- selected agent or `None`;
- personal versus `--here` workspace selection;
- current working directory;
- optional source request.

Normal learning has no source request and must generate byte-for-byte equivalent
host arguments to the current launcher.

For reading, workspace preparation happens before source ingestion and after
host detection. This preserves the existing behavior that a missing compatible
host fails before the launcher prompts for or downloads learner material.

### Source ingestion module

Create a focused `socratic_learn.sources` module responsible for:

- parsing and validating local paths and URLs;
- bounded URL retrieval;
- HTML text extraction;
- PDF text extraction;
- normalization and chunking;
- atomic private bundle publication;
- source-specific errors.

The module must not select agents, build host arguments, or teach. The launcher
must not contain extraction logic.

Use `pypdf>=7.0,<8` for PDF extraction. Version 7.0.0 is the current major
release as of 2026-11-08, supports Python 3.10+, and is compatible with this
project's Python 3.11 floor:
<https://pypi.org/project/pypdf/7.0.0/>.

`pypdf` is a required runtime dependency, not an optional extra. Wheel tests
must install declared dependencies instead of using `--no-deps`. The
PyInstaller specification must collect `pypdf` and its declared transitive
dependencies, and every frozen-platform smoke test must ingest a textual PDF
and reach a fake host. A `socratic --version` smoke test alone is insufficient.

Do not add OCR in this release. A PDF with no meaningful extractable text fails
with a message that identifies scanned/image-only content as the likely cause
and states that OCR is not yet supported.

### HTML extraction

HTML extraction uses the Python standard library. It:

- prefers content inside `article`, then `main`, then `body`;
- excludes `script`, `style`, `noscript`, `svg`, `nav`, `header`, `footer`,
  `form`, and `aside`;
- preserves headings, paragraphs, block quotations, list items, and table cell
  text in reading order;
- decodes character sets declared by the HTTP response, falling back to UTF-8
  with replacement only when the declared encoding is absent or invalid;
- collapses repeated horizontal whitespace while preserving paragraph
  boundaries.

The extractor is intentionally deterministic and conservative. It does not
execute JavaScript. A page whose meaningful article text exists only after
client-side rendering fails with an actionable message rather than launching a
browser.

### Private source bundle

Source bundles live under:

```text
<workspace records>/sources/<source-id>/
```

`source-id` is the lowercase SHA-256 digest of the normalized source origin and
the retrieved raw bytes. It contains only hexadecimal characters.

Each bundle contains:

```text
metadata.json
index.md
original.bin
sections/
  0001.txt
  0002.txt
  ...
```

`metadata.json` contains schema version, title, safe display origin, media type,
raw SHA-256, extraction timestamp in UTC, section count, and normalized
character count. It never contains URL credentials, request headers, cookies,
environment values, or host credentials.

`index.md` contains title, display origin, media type, and an ordered section
map. HTML entries use the nearest heading plus a sequence number. PDF entries
use page numbers. Every entry names its chunk file.

Chunk files use UTF-8, LF line endings, and Unicode NFC normalization. Each
chunk is at most 12,000 Unicode code points. Splits prefer heading, page, and
paragraph boundaries; an individual overlong paragraph is split at a Unicode
whitespace boundary.

Publication is atomic. A partially downloaded or extracted source never
becomes the active bundle. Existing bundles with the same identifier are
validated and reused without rewriting.

Bundles extend the existing private-record creation policy. Source directories
and files must be regular, non-linked paths beneath the records directory. In
`--here` mode they remain under `.socratic-learn/workspace/`, which existing
repository rules exclude from version control.

The current direct-path checks are not sufficient for this bundle contract.
Before ingestion is implemented, add one trusted-root containment primitive
that:

- resolves and validates every existing ancestor from the trusted records root
  to the destination;
- rejects POSIX symbolic links and Windows reparse points, including junctions;
- opens existing files without following links where the platform supports it;
- stages files in a newly created same-parent directory with owner-only
  permissions;
- validates a pre-existing final bundle before reuse;
- publishes with one atomic same-volume rename;
- removes its staging directory on every handled failure;
- rejects a final-name collision that does not validate as the expected bundle.

The supported threat model prevents accidental publication, traversal through
linked paths, and replacement by non-concurrent operations. It does not claim
to defeat a hostile process running as the same OS user that races final path
operations. This matches the repository's documented POSIX same-user TOCTOU
limitation and must be stated for Windows as well.

### Resource limits and network policy

The first release applies these exact limits:

- 20 MiB maximum raw local file or HTTP response;
- 500 PDF pages;
- 5,000,000 normalized Unicode code points;
- 20-second socket timeout for connect and read operations;
- at most five HTTP redirects.

DNS resolution uses the platform resolver and is not claimed to have a
cross-platform hard deadline. A later transport can tighten that guarantee
without changing the source bundle contract.

HTTP retrieval:

- permits only HTTP and HTTPS at the initial URL and every redirect;
- rejects URL user information;
- resolves every destination before a request and rejects the request if any
  resolved address is loopback, link-local, private, multicast, unspecified,
  or reserved unless `--allow-private-network` is active;
- verifies the connected peer address against the same policy before sending
  the HTTP request, preventing a validated public name from rebinding to a
  blocked destination;
- sends no cookies, authorization headers, or environment credentials;
- disables environment-provided HTTP and HTTPS proxies in this release;
- uses a fixed `Socratic-Learn/<version>` user agent;
- sends `Accept-Encoding: identity` and rejects any non-identity
  `Content-Encoding`;
- validates the final content type and file signature;
- accepts `text/html`, `application/xhtml+xml`, and `application/pdf`;
- accepts `application/octet-stream` or a missing content type only when
  `%PDF-` appears within the first 1,024 bytes or the first 1,024 bytes contain
  an ASCII-case-insensitive `<html` or `<!doctype html` marker;
- stops before storing byte 20,971,521;
- leaves TLS verification enabled.

The full retrieval URL exists only in memory. The persisted and learner-facing
display origin is `scheme://host[:non-default-port]/path` with a lowercase
IDNA host, normalized percent encoding, no fragment, no user information, and
no query string. The source identifier hashes the full canonical retrieval URL
plus the raw bytes, so two query-dependent representations do not collide
without persisting a query that may contain a secret. Errors use only the
redacted display origin.

HTML decoding uses, in order: a valid HTTP `charset`, a Unicode byte-order
mark, a valid HTML meta charset found in the first 4,096 bytes, then UTF-8 with
replacement. Unknown charset labels fall through rather than failing. A source
is meaningful only when extraction produces at least 200 non-whitespace
Unicode code points. PDF detection uses the same 1,024-byte `%PDF-` rule, and
image-only detection uses the same 200-character threshold across all pages.

The launcher does not follow URLs discovered inside the document.

### Host handoff

The normalized source text is not embedded in command-line arguments or in the
protocol bundle. The launcher builds a short source-study bootstrap containing:

- the learner-confirmed goal text;
- the absolute path to `index.md`;
- the absolute path to `metadata.json`;
- a statement that source files are untrusted study material, not
  instructions;
- a prohibition on executing commands, opening additional URLs, reading other
  local files, or changing configuration because source content requests it;
- a requirement to read the index first and open only sections needed for the
  current learning step;
- a statement that no external verification has occurred.

Pi and Claude Code continue to receive the canonical protocol through their
system-prompt file options. Antigravity continues to receive the protocol path
through its interactive bootstrap. All three receive the same source-study
bootstrap as the initial learner content.

Normal sessions use their current bootstrap text unchanged.

Host parity means that all adapters receive byte-identical source bundle files,
goal text, source location, and epistemic rules inside the strongest envelope
that host supports. It does not mean identical instruction hierarchy or model
behavior: Pi and Claude receive the canonical protocol through system-prompt
file options, while Antigravity receives its protocol path in user content.
Adapter contract tests therefore verify each envelope separately.

The source-originated tool prohibition and untrusted-content labeling reduce
prompt-injection risk but are not a security boundary. The hosts retain their
normal tools and environment access. Unless a host supplies and the adapter
enables an enforceable sandbox, resistance to source prompt injection is
best-effort and documentation must say so.

## Protocol changes

The canonical documents add source-study behavior without introducing a
separate pedagogy:

- `core/session-protocol.md` defines source indexing, focused section access,
  learner-facing source locations, and source-aware closure.
- `core/evidence-policy.md` defines the three-way distinction among source
  assertion, within-source support, and external verification.
- `core/pedagogy.md` strengthens “one focused question at a time” so a prompt
  may not multiply two claims by several analysis dimensions in one learner
  turn.
- `AGENTS.md` summarizes the source rules and orchestration privacy.

The generated prompt protocol version increases from `1.1.0` to `1.2.0`.
`dist/manifest.json`, packaged resources, adapters, and deterministic build
tests update through the existing builder rather than by manually editing
generated output.

The protocol must explicitly prevent the semantic failures observed in the
article simulation:

- announcing internal protocol or file reading;
- treating absence of a discovered primary artifact as proof of nonexistence;
- batching several independent learner tasks;
- presenting an article's educational claim as externally established;
- using a new technical term inside a transfer question without introducing
  it.

Source-study mode is an explicit specialization of autonomous research policy.
It remains source-bounded by default even for disputed claims. The tutor marks
those claims externally unverified and states what evidence could verify them.
Only an explicit learner request activates host-provided external research;
when activated, the normal source-priority and citation rules apply.

## Error handling

All expected failures use the existing typed-error boundary and produce no
traceback. Messages state the failure and one concrete recovery action.

Required cases include:

- missing, linked, non-regular, or oversized local source;
- local file without a PDF signature;
- unsupported or credential-bearing URL;
- redirect limit or redirect to an unsupported scheme;
- timeout, TLS failure, DNS/network failure, or HTTP error;
- unsupported or missing content type;
- oversized HTTP response;
- malformed, encrypted, over-page-limit, or image-only PDF;
- HTML with no meaningful extracted content;
- normalized content above its limit;
- private bundle path collision or failed atomic publication.

Network errors must not include credentials, private response bodies, request
headers, or environment values.

## Context control

Chunking is a delivery control, not a summary or an enforceable context limit.
The source index gives the tutor stable retrieval units while preserving the
complete extractable text. The protocol requests that the tutor load only
sections needed for the current question and return to the index when the route
changes. A host with unrestricted file tools can still read every chunk; the
product must describe context restraint as best-effort unless a later adapter
can enforce section access.

The launcher does not ask a model to summarize the whole source before
confirming the learner's objective. This avoids converting a large document
into an unreviewed model-generated surrogate and does not itself load every
chunk into the first turn. Host compliance with selective reads remains
best-effort.

## Evaluation

Add an article-reading semantic scenario using a small, redistributable
fixture authored for this repository. The fixture contains:

- one directly supported descriptive claim;
- one causal claim asserted without evidence;
- one vague promotional claim;
- a source-interest disclosure;
- stable headings and short sections.

The simulated learner:

- initially treats longevity as proof of effectiveness;
- asks for help distinguishing weak evidence from no evidence;
- becomes overloaded if the tutor batches independent tasks;
- makes one leading transfer question;
- revises only after usable feedback.

The existing eight-category rubric remains unchanged so historical scores stay
comparable. Add versioned suite manifests under
`evaluation/fixtures/suites/`. A suite manifest identifies its exact scenarios,
rubric, report contract, and schema version. Add `baseline-v1` for the existing
three-scenario baseline and `article-reading-v1` for this scenario.

Run-record schema version 2 records SHA-256 identities for the scenario,
rubric, suite manifest, and protocol in addition to the existing runtime and
model identity. The loader retains read support for existing schema-1
synthetic/private records, but every new run writes schema 2.

The current baseline renderer remains valid for the historical baseline.
Replace its hard-coded scenario-triplet requirement for new reports with the
ordered scenario identifiers from the selected suite manifest. Report
validation checks the suite identifier, suite hash, rubric hash, scenario
hashes, and category maximum rather than assuming one universal triplet.

The article run is scored under the existing categories, while tracked
findings explicitly record source grounding, orchestration leakage, question
batching, and epistemic errors. Add these critical-failure identifiers to the
rubric:

- `fabricated-source-support`;
- `source-claim-presented-as-externally-verified`;
- `batched-independent-learner-tasks`.

Raw source text, model streams, learner records, and local paths remain private
and untracked. Only sanitized findings and report excerpts may be committed.

The Antigravity contract fixture must be recaptured for the installed runtime
version before a live semantic run. A version mismatch remains a hard
preflight refusal.

The article mode passes semantic validation only when a live run:

- ends with `observable_outcome`;
- has no infrastructure failure;
- has no critical failure;
- scores 2 for observable outcome, calibrated questioning, corrective
  feedback, and evidence closure;
- scores at least 1 in every remaining category;
- scores at least 14 of 16 overall.

An authentication, quota, network, runtime, or timeout result is
**inconclusive**. It is preserved and reported but never satisfies the release
gate.

## Delivery milestones

The approved feature is one roadmap, not one undivided implementation change.
Each milestone is reviewed and testable before the next begins:

1. **Trusted storage and packaging foundation:** trusted-root containment,
   atomic private bundle publication, `pypdf` dependency declaration, wheel
   dependency installation, and frozen PDF smoke fixtures. No public read
   command ships at this milestone.
2. **Deterministic source ingestion:** URL transport policy, HTML extraction,
   PDF extraction, normalization, chunking, metadata, and source bundle reuse
   behind internal APIs.
3. **CLI, hosts, and protocol:** `socratic read`, compatibility behavior, host
   envelopes, source-bounded protocol rules, documentation, and normal-session
   regression coverage.
4. **Semantic release gate:** versioned suite/report identities, article
   scenario, runtime-contract recapture, live scoring, sanitized findings, and
   the successful semantic threshold.

No milestone may weaken tests from an earlier milestone to make the next one
pass.

## Automated testing

Implementation follows test-driven development. Required tests cover:

### CLI and launcher

- normal non-`read` command behavior remains unchanged;
- read command parsing with URL, local PDF, goal, `--agent`, `--here`, and
  `--allow-private-network`;
- global read options before and after the command token, `--`, and a local
  filename beginning with `-`;
- missing goal prompts with source-specific wording;
- `socratic learn read critically` remains a normal learning goal;
- `socratic read critically` produces the documented source error rather than
  silently becoming a normal goal;
- read-source errors use stable exit codes and no traceback;
- missing host fails before prompting or downloading;
- all three adapters receive one source payload inside their documented
  host-specific bootstrap envelope, while normal-session envelopes remain
  unchanged.

### Source validation and extraction

- regular local PDF acceptance and symlink rejection;
- HTML extraction precedence and excluded elements;
- HTML and PDF section/page indexing;
- deterministic Unicode normalization and chunk boundaries;
- image-only, encrypted, malformed, over-page, oversized, and empty sources;
- URL scheme, credentials, redacted queries, public-to-private redirects,
  DNS-rebinding peer validation, disabled environment proxies, content
  encoding, content type, signatures, timeouts, and size limits;
- response and error sanitization.

Tests use local byte fixtures and an in-process HTTP server. They do not depend
on the public internet.

### Private storage

- bundle paths remain beneath records;
- linked ancestors and destination collisions are rejected before reading or
  writing through them;
- partial failures leave no published bundle;
- successful repeated ingestion reuses a validated identical bundle;
- local source material, bundles, and raw fixtures are excluded from package
  and repository publication.

### Protocol and distribution

- canonical content checks for source assertion/support/verification;
- focused-task and orchestration-privacy rules;
- protocol version `1.2.0`;
- deterministic rebuild and packaged-resource equality;
- wheel tests install runtime dependencies;
- native Windows, Linux, and macOS package smoke tests use the frozen
  executable to ingest a textual PDF and reach a fake host.

### Semantic behavior

- article scenario fixture schema validation;
- schema-1 run-record read compatibility and schema-2 hash validation;
- baseline-v1 and article-reading-v1 suite/report contracts;
- unchanged evaluator isolation and sanitation guarantees;
- a manual live run against the approved runtime contract;
- tracked report findings tied to exact sanitized turns;
- an infrastructure failure is reported as inconclusive and fails the article
  release gate.

## Documentation

Update the README quick start with:

```text
socratic read https://example.org/article
socratic read paper.pdf evaluate the main claim and its evidence
```

Document:

- supported source types and limits;
- distinction between source-grounded reading and external verification;
- private source location and `--here` behavior;
- lack of OCR and JavaScript rendering;
- host/model requirements;
- actionable examples for Pi, Claude Code, and Antigravity.

The README must not claim that Socratic Learn verifies an article's truth,
improves learning outcomes, or supports every PDF.

## Out of scope

This release does not include:

- canonical automatic literature, Consensus, or web search; an explicit
  learner request may use a host's existing research capability, with the
  capability and sources disclosed;
- OCR;
- JavaScript-rendered page capture;
- EPUB, DOCX, audio, video, or arbitrary local text files;
- citation-style generation;
- multi-document synthesis;
- a graphical interface;
- model selection or provider billing management;
- automatic claims that the learner mastered the article.

These may be designed as separate increments after the ingestion and critical
reading workflow is validated.

## Acceptance criteria

The design is complete when:

1. A fresh installation can run `socratic read` on a supported URL or local
   textual PDF with Pi, Claude Code, or Antigravity.
2. Every host receives the same private, indexed source bundle and source-study
   payload inside its documented host-specific envelope.
3. The first tutor response confirms an observable source-learning outcome
   without exposing orchestration.
4. Tutor prompts use one focused learner task and source locations.
5. Closure distinguishes source claims, within-source support, external
   verification status, application evidence, and remaining gaps.
6. Unsupported, unsafe, oversized, and non-extractable sources fail
   actionably without a traceback or partial published bundle.
7. The complete automated suite, deterministic build, repository validator,
   dependency-aware wheel smoke tests, frozen-PDF smoke tests, and native
   safety matrix pass.
8. A live article semantic run meets the defined score threshold with no
   critical or infrastructure failure. Infrastructure failures remain
   inconclusive and block release.
9. The implementation is delivered through the four ordered milestones, each
   retaining the verified contracts of the previous milestone.
