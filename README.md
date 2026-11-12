# Socratic Learn

**Turn any AI agent into a tutor that checks whether you actually learned.**

Socratic Learn helps you learn any subject through a guided conversation that
ends in application. It works for any subject or skill, including physics,
programming, writing, and research.

**Any subject** | **Your AI host** | **Progress through application**

```text
socratic "I want to learn how attention works"
```

[Install Socratic Learn](#quick-start)

[Python 3.11+](https://www.python.org/downloads/) | [License: MIT](LICENSE)

## See a session

Socratic Learn starts by turning a broad interest into something you can
demonstrate. It checks only the knowledge needed for that outcome and gives
help when the next step cannot reasonably be discovered.

```text
Learner  > I want to understand why attention scales by sqrt(d_k).
Tutor    > What should you be able to derive or predict by the end?
Learner  > I want to derive the scaling and predict what changes without it.
Tutor    > I'll check the starting point first. For one term in the dot
           product, what variance would you expect if its two factors are
           independent and standardized?
           I'll use your answer to set the route. You can redirect me at any time.
...
Evidence > The learner derives the variance growth and applies it to a changed
           dimension without receiving the final answer first.
```

The tutor asks when you have enough information to reason forward. When a
missing fact blocks you, it explains that fact and returns control with a new
application.

## Why it is different

The conversation adapts to your work, not to a personality label. A preference
for diagrams, prose, code, or concrete examples can change the presentation.
It does not prove mastery or define a fixed learning style. Progress comes from
what you can explain, derive, predict, implement, or diagnose.

Support also changes with the evidence in the session. The tutor can offer a
cue, a simpler case, another representation, or a direct explanation. After
stronger help, it asks you to retrieve or apply the idea again. When you return
later, the next session starts from a recorded gap instead of replaying the
previous answer.

If you have limited time, the route becomes smaller while keeping one final
application. The aim is an honest partial result rather than a rushed claim of
completion.

I built Socratic Learn out of a recurring need in my work as an AI researcher.
I wanted a practical way to learn new theory and tools without mistaking a
fluent explanation for understanding. Mathematics and AI are starter curricula,
but they are examples rather than product boundaries.

## Quick start

Normal use requires no repository clone and no source build. The native
installers target x86-64 Windows, Linux, and macOS.

Native installation is available only after GitHub Release v0.1.0 is published.
When that release exists, download its exact installer to a temporary file and
review it before running it.

Windows PowerShell:

```powershell
$installer = Join-Path $env:TEMP "socratic-install-v0.1.0.ps1"
Invoke-WebRequest https://github.com/marcos-guilherme/socratic-learn/releases/download/v0.1.0/install.ps1 -OutFile $installer
Get-Content $installer
```

After reviewing the file:

```powershell
& $installer
```

Linux or macOS:

```sh
installer=$(mktemp)
curl -fL https://github.com/marcos-guilherme/socratic-learn/releases/download/v0.1.0/install.sh -o "$installer"
cat "$installer"
```

After reviewing the file:

```sh
sh "$installer"
rm -f "$installer"
```

The installers verify release hashes before publication. The first native
binaries are unsigned and may trigger Windows SmartScreen or macOS Gatekeeper.
A checksum confirms the downloaded bytes, but it does not replace code signing.

For another architecture, or for a Python-managed installation, use pipx after
package publication. The pipx command is available only after socratic-learn
0.1.0 is published on PyPI.

```text
pipx install socratic-learn
```

Start without putting your learning goal in shell history:

```text
socratic
```

You can also pass a goal or choose a host directly:

```text
socratic "I want to learn linear algebra"
socratic --agent pi
```

Starting without a goal is the privacy default. Socratic Learn does not store
provider credentials. The chosen host keeps its own authentication and model
settings.

Personal sessions use
`~/.socratic-learn/learning/.socratic-learn/workspace/`. To use the current
directory as the learning project, run:

```text
socratic --here
```

## Choose an AI host

Socratic Learn provides the learning method and private workspace. The launcher
host provides the interactive terminal and access to a provider and model.
Pi, Claude Code, and Antigravity are launcher hosts. They keep their own
authentication, quotas, tools, and model selection.

Pi offers a general interactive harness. Antigravity can be launched through
its `agy` command. Claude Code uses its own terminal experience. Cursor remains
a project integration rather than a launcher choice.

Native installations manage their own lifecycle. Pipx installations print the
matching pipx command instead of changing their environment.

```text
socratic update
socratic uninstall
```

## Learn from an article

`socratic learn` starts a general session. `socratic read` prepares one HTML or
XHTML page, or a textual PDF, for focused study.

```text
socratic read https://example.org/article
socratic read paper.pdf evaluate the main claim and its evidence
socratic read --agent pi tests/fixtures/sources/minimal-text.pdf explain its evidence
```

For a local development server or private network, add the explicit gate:

```text
socratic read --allow-private-network http://localhost/article
```

Socratic Learn creates the source bundle and shared study prompt. The launcher
host still owns the provider, model, credentials, quota, and optional research
tools.

Private bundles live under
`~/.socratic-learn/learning/.socratic-learn/workspace/sources/<source-id>/`.
With `--here`, they live under
`PROJECT/.socratic-learn/workspace/sources/<source-id>/`. Each bundle contains
an index, metadata, normalized sections, and the original bytes. Identical
input reuses a validated bundle instead of publishing a duplicate.

Supported input is HTTP or HTTPS HTML, XHTML, and regular local PDF files:

| Limit | Value |
| --- | --- |
| Raw input | 20 MiB |
| PDF length | 500 PDF pages |
| Extracted text | 5,000,000 Unicode code points |
| Socket timeout | 20-second read timeout |
| Redirects | five redirects |
| Section chunk | 12,000 code points |

There is no OCR and no JavaScript rendering. Image-only PDFs, encrypted PDFs,
and dynamic pages that need a browser are rejected with an actionable message.

Study is source-bounded by default. The tutor separates a source assertion,
within-source support, and external verification. External research requires an
explicit learner request, and the tutor must disclose the capability and
sources it used.

Source text is untrusted study material. Prompt-injection resistance and tool
restraint are best-effort controls, not a sandbox. The selected host may still
have network or shell access under its own policy.

For an image-only PDF, use a textual export. For dynamic pages, save a static
page or PDF. A quota or model error belongs to the host provider. For changing
agents, pass `--agent` or update `~/.socratic-learn/config.json`.

## How the method works

The protocol follows one connected path:

`objective → prerequisites → guided route → application → evidence`

1. **Define the outcome.** Turn the topic into something you can demonstrate.
2. **Find the starting point.** Check only prerequisites that could block it.
3. **Preview the route.** Explain what comes first and why, then start teaching
   automatically. You can redirect at any time.
4. **Teach adaptively.** Ask when you can reason forward and explain when
   required information is missing.
5. **Require evidence.** Close after an application, with remaining gaps and a
   useful next step.

The learning behavior is defined in [pedagogy](core/pedagogy.md), the
[session protocol](core/session-protocol.md),
[assessment](core/assessment.md), and the
[evidence policy](core/evidence-policy.md).

## Research and limitations

The [learner preference catalog](docs/research/learner-preference-patterns.md)
separates preference, engagement, and measured learning. The project uses that
distinction to adapt presentation without treating confidence or activity as
mastery evidence.

Research that informed specific design decisions includes
[Mahoney et al. (2023)](https://doi.org/10.1016/j.tsc.2023.101422),
[Munshi et al. (2023)](https://doi.org/10.1111/jcal.12761),
[Borchers et al. (2025)](https://doi.org/10.1016/j.compedu.2025.105364),
[van den Broek et al. (2025)](https://doi.org/10.1016/j.learninstruc.2025.102196),
[Stogniy et al. (2020)](https://doi.org/10.1096/fasebj.2020.34.s1.04148), and
[Lee et al. (2025)](https://doi.org/10.48550/arXiv.2509.16262).

Those studies examine their own learners, settings, and teaching methods. They
do not validate Socratic Learn as a complete product or guarantee mastery.

The first semantic baseline ran three unchanged-protocol Antigravity sessions.
All three stopped before a learner response because the host denied the same
workspace command. For that reason, no pedagogy score was assigned. The
[sanitized baseline report](evaluation/reports/2026-11-06-antigravity-baseline.md)
records the result without publishing raw learner evidence.

## Technical documentation

The runtime is dependency-light Python 3.11+ with `pypdf` for textual PDF
extraction. The checked-in prompt bundle and manifest are deterministic.
Learner profiles, progress, source bundles, and raw evaluation streams remain
private and excluded from published packages.

Installation protects against ordinary collisions, accidental concurrent
changes, and cooperating Socratic Learn processes. On POSIX systems, hostile
processes running as the same OS user are outside the threat model. A final-path
TOCTOU window remains because a final path mutation cannot be tied to an inode
that is already open. Ambiguous paths are preserved for manual recovery.

Contributors can clone and build the source:

```powershell
git clone https://github.com/marcos-guilherme/socratic-learn.git
cd socratic-learn
python -m socratic_learn build
```

To create the ignored example workspace:

```powershell
Copy-Item -Recurse workspace.example\* workspace
```

```sh
cp -R workspace.example/. workspace/
```

- [Installation and lifecycle](docs/universal-installation.md)
- [Launcher host contract](docs/launcher-adapters.md)
- [Adding an adapter](docs/adding-an-adapter.md)
- [Manifest reference](docs/manifest-reference.md)
- [Cursor adapter](adapters/cursor/README.md)
- [Claude Code adapter](adapters/claude-code/README.md)
- [Pi adapter](adapters/pi/README.md)
- [Native CI workflow](.github/workflows/native-python.yml)

## License

Socratic Learn is available under the [MIT License](LICENSE).
