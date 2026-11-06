---
name: socratic-learn
description: Run diagnostic, evidence-aware learning sessions for any subject or skill.
---

Before starting any learning session, read and follow `{{PATH_BASE}}.socratic-learn/socratic-learn.prompt.md`.

Capability mapping:
- Structured questions: use Cursor's structured question UI when available; otherwise ask in conversation.
- Web: verify volatile claims with primary sources using available web tools; otherwise mark them unverified.
- Visuals: use Mermaid when available; otherwise use text.
- Filesystem: keep private learner state under `{{PATH_BASE}}.socratic-learn/workspace/` and out of version control; if unavailable, return the record in conversation.
