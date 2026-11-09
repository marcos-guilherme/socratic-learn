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
```

`SOURCE` accepts:

- an `http://` or `https://` URL whose response is HTML or PDF;
- a local regular PDF file.

The command rejects unsupported URL schemes, directories, symbolic links,
non-PDF local files, missing files, and URLs containing user information.

If `GOAL` is absent, the launcher asks:

```text
What do you want to be able to do with this source?
```

An empty answer is rejected. The launcher never invents a learning objective
from the source title.

The existing command shape remains unchanged:

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
6. includes source-grounded application or transfer before closure.

The tutor does not narrate that it is reading prompts, rules, protocols, or
internal files.

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
- `--here`.

Argument abbreviation remains disabled. Existing normal, administrative,
update, and uninstall commands retain their current behavior and error codes.

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

Files use the existing private-record creation policy. Source directories and
files must be regular, non-linked paths beneath the records directory. In
`--here` mode they remain under `.socratic-learn/workspace/`, which existing
repository rules exclude from version control.

### Resource limits and network policy

The first release applies these exact limits:

- 20 MiB maximum raw local file or HTTP response;
- 500 PDF pages;
- 5,000,000 normalized Unicode code points;
- 20-second connection timeout;
- 60-second total retrieval deadline;
- at most five HTTP redirects.

HTTP retrieval:

- permits only HTTP and HTTPS at the initial URL and every redirect;
- rejects URL user information;
- sends no cookies, authorization headers, or environment credentials;
- uses a fixed `Socratic-Learn/<version>` user agent;
- validates the final content type and file signature;
- accepts `text/html`, `application/xhtml+xml`, and `application/pdf`;
- rejects compressed response expansion beyond the raw limit;
- leaves TLS verification enabled.

Because this is a local command acting on a URL explicitly supplied by the
local user, loopback and private-network hosts are not blocked. The launcher
does not follow URLs discovered inside the document.

### Host handoff

The normalized source text is not embedded in command-line arguments or in the
protocol bundle. The launcher builds a short source-study bootstrap containing:

- the learner-confirmed goal text;
- the absolute path to `index.md`;
- the absolute path to `metadata.json`;
- a statement that source files are untrusted study material, not
  instructions;
- a requirement to read the index first and open only sections needed for the
  current learning step;
- a statement that no external verification has occurred.

Pi and Claude Code continue to receive the canonical protocol through their
system-prompt file options. Antigravity continues to receive the protocol path
through its interactive bootstrap. All three receive the same source-study
bootstrap as the initial learner content.

Normal sessions use their current bootstrap text unchanged.

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

Chunking is a delivery control, not a summary. The source index gives the tutor
stable retrieval units while preserving the complete extractable text. The
protocol instructs the tutor to load only sections needed for the current
question and to return to the index when the route changes.

The launcher does not ask a model to summarize the whole source before
confirming the learner's objective. This avoids converting a large document
into an unreviewed model-generated surrogate and prevents the first turn from
loading every chunk.

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

The existing eight-category rubric remains unchanged so historical baseline
scores remain comparable. The run is scored under the existing categories,
while tracked findings explicitly record source grounding, orchestration
leakage, question batching, and epistemic errors. Add these critical-failure
identifiers to the rubric:

- `fabricated-source-support`;
- `source-claim-presented-as-externally-verified`;
- `batched-independent-learner-tasks`.

Raw source text, model streams, learner records, and local paths remain private
and untracked. Only sanitized findings and report excerpts may be committed.

The Antigravity contract fixture must be recaptured for the installed runtime
version before a live semantic run. A version mismatch remains a hard
preflight refusal.

## Automated testing

Implementation follows test-driven development. Required tests cover:

### CLI and launcher

- normal command behavior remains unchanged;
- read command parsing with URL, local PDF, goal, `--agent`, and `--here`;
- missing goal prompts with source-specific wording;
- `socratic learn read critically` remains a normal learning goal;
- read-source errors use stable exit codes and no traceback;
- missing host fails before prompting or downloading;
- all three adapters receive one unchanged goal/source bootstrap argument.

### Source validation and extraction

- regular local PDF acceptance and symlink rejection;
- HTML extraction precedence and excluded elements;
- HTML and PDF section/page indexing;
- deterministic Unicode normalization and chunk boundaries;
- image-only, encrypted, malformed, over-page, oversized, and empty sources;
- URL scheme, credentials, redirects, content type, signatures, deadlines, and
  size limits;
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
- native Windows, Linux, and macOS package smoke tests include `pypdf`.

### Semantic behavior

- article scenario fixture schema validation;
- unchanged evaluator isolation and sanitation guarantees;
- a manual live run against the approved runtime contract;
- tracked report findings tied to exact sanitized turns.

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

- automatic literature, Consensus, or web search;
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
   bootstrap.
3. The first tutor response confirms an observable source-learning outcome
   without exposing orchestration.
4. Tutor prompts use one focused learner task and source locations.
5. Closure distinguishes source claims, within-source support, external
   verification status, application evidence, and remaining gaps.
6. Unsupported, unsafe, oversized, and non-extractable sources fail
   actionably without a traceback or partial published bundle.
7. The complete automated suite, deterministic build, repository validator,
   and native safety matrix pass.
8. A live article semantic run completes or records an infrastructure failure
   without converting that failure into a pedagogy score.
