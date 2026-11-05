# Claude Code Adapter

Use [CLAUDE.md](CLAUDE.md) in this directory as the adapter source. Its `../../` links are relative to this directory, so **do not copy that file unchanged to a project root**.

For a project with this repository layout, save the following snippet as `<project-root>/CLAUDE.md`, or paste it into an existing root loader. These links are deliberately relative to the project root:

<!-- root-loader:start -->
```markdown
# Learning Tutor Loader

Before a learning session, read the universal [agent entry](AGENTS.md) and the canonical [pedagogy](core/pedagogy.md), [session protocol](core/session-protocol.md), [assessment](core/assessment.md), and [evidence policy](core/evidence-policy.md), then follow that shared protocol.

When no structured quiz is available, ask one conversational question at a time. Use configured web tools for volatile facts. Read and write real learner state only under `workspace/`.
```
<!-- root-loader:end -->

If copying the adapter file instead, rewrite `../../AGENTS.md` to `AGENTS.md` and every `../../core/...` target to `core/...`. Keep `workspace/` relative to the project root.

The loader delegates to the universal [agent entry](../../AGENTS.md) and canonical [pedagogy](../../core/pedagogy.md), [session protocol](../../core/session-protocol.md), [assessment](../../core/assessment.md), and [evidence policy](../../core/evidence-policy.md); it does not replace them.
