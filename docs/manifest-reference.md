# Manifest Reference

`dist/manifest.json` is deterministic UTF-8 JSON with LF line endings and one
trailing newline. Unknown or missing fields are invalid. The checked-in
manifest is the concrete reference; rebuild it with:

```powershell
python -m socratic_learn build
```

## Top-level fields

- `schema_version`: integer `2`. Readers reject other schema versions.
- `product`: exact identifier `socratic-learn`.
- `protocol_version`: exact protocol version `1.0.0`. Protocol behavior changes
  require an explicit version change and compatible readers.
- `language`: `en`, identifying the language of generated instructions.
- `targets`: the ordered array `generic`, `cursor`, `claude-code`, and `pi`.
- `sources`: ordered canonical source records. Each record has only `path` and
  `sha256`.
- `bundle`: generated prompt record with only `path` and `sha256`.
- `capability_fallbacks`: required behavior when `cross_session_memory`,
  `diagram_rendering`, `filesystem`, `structured_quiz`, `subagents`, or `web`
  is unavailable.
- `conformance`: behavioral contract metadata with `version` and
  `required_diagnostic_codes`.
- `session_headings`: the exact ordered headings required in a session record.

## Source records and hashes

Each `sources[].path` is a control-free relative POSIX path such as
`core/pedagogy.md`; absolute paths, `..`, backslashes, and drive-qualified
paths are prohibited. `sources[].sha256` is lowercase SHA-256 over the source
bytes after deterministic build normalization: UTF-8 decoding, CRLF/CR to LF,
removal of leading and trailing blank lines, and exactly one trailing newline.

The current manifest lists four canonical core files followed by the
curriculum maps. Source order contributes to bundle order.

The current source list includes the mathematics and AI starter curriculum
maps. They are bundled examples and dependency guides, not a restriction on
the subjects or skills the protocol can support.

## Bundle record

`bundle.path` is exactly `socratic-learn.prompt.md`.
`bundle.sha256` is lowercase SHA-256 over the exact generated bundle bytes,
including its LF line endings and final newline. The bundle begins with
`# Socratic Learn` and embeds source boundary markers. Installers
verify the bundle hash before planning any publication.

## Conformance and session fields

`conformance.version` is integer `1`.
`conformance.required_diagnostic_codes` is the exact ordered set of behavioral
checks enforced by the builder, including observable outcome, bounded
diagnosis, approval before teaching, responsive follow-up, active return after
exposition, evidence-based closure, private state, capability fallbacks, and
evidence rules.

`session_headings` contains these exact values in order:

```text
## Outcome
## Diagnostic evidence
## Approved dependency path
## Concepts established
## Application evidence
## Remaining gaps
## Next step
## Sources
```

## Version policy

Schema version describes the JSON shape and validation rules. Protocol version
describes tutor behavior. This release accepts only schema `2` and protocol
`1.0.0`; it does not silently migrate unknown versions. Generated artifacts,
install receipts, and runtime code must agree before installation or update.

Schema-2 installation receipts are separate from the distribution manifest.
They contain exactly `schema_version`, `product`, `protocol_version`, `target`,
`owned_paths`, and `hashes`. The product is exactly `socratic-learn`. Receipt
hashes cover every owned file except the receipt itself and authorize updates
only while those bytes remain intact. Schema-1 Learning Tutor receipts remain
readable only for verified migration.
