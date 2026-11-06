---
name: learning-tutor
description: Run a project-local learning session with the universal tutor.
---

Before starting any learning session, read and follow `{{PATH_BASE}}.learning-tutor/learning-tutor.prompt.md`.

Capability mapping:
- Questions: use the optional quiz tool for assessed questions, a preference question when no answer is objectively correct, and conversation when tools are unavailable.
- Research: use available research and web tools for primary-source verification; otherwise mark volatile claims unverified.
- Visuals: use visual makers when available; otherwise use a text description.
- State: use md-log or filesystem tools to keep private learner state under `{{PATH_BASE}}.learning-tutor/workspace/` and out of version control; otherwise return the record in conversation.
