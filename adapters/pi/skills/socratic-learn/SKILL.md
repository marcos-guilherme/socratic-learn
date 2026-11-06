---
name: socratic-learn
description: Conducts diagnostic, evidence-aware learning sessions for any subject or skill. Use when the user wants to study, understand, practice, or build a learning plan. Mathematics and AI are included starter curricula, not limits.
---

# Socratic Learn

This file is the repository-layout source and uses links relative to its
adapter directory. For installation at
`<project>/.pi/skills/socratic-learn/SKILL.md`, follow the
[Pi installation procedure](../../README.md) and copy the adjacent
[project-install template](SKILL.project.md.template), not this file.

Load the universal [agent entry](../../../../AGENTS.md) and canonical [pedagogy](../../../../core/pedagogy.md), [session protocol](../../../../core/session-protocol.md), [assessment](../../../../core/assessment.md), and [evidence policy](../../../../core/evidence-policy.md). The universal protocol applies to any subject or skill. Consult the [mathematics map](../../../../curricula/mathematics/map.md) and [AI map](../../../../curricula/ai/map.md) when relevant.

## Pi capability mapping

- Use `quiz` for graded checks. Without it, conduct each check conversationally and grade the response from the observable evidence.
- Use `ask-user-question` for preference and goal decisions. Without it, ask the decision directly in conversation.
- Use a researcher subagent to verify volatile facts. Without one, use available web tools directly; without web access, apply the evidence policy's no-web fallback.
- Use Mermaid or SVG makers only for structure or geometry. Without them, use Mermaid text when renderable or a concise textual edge list.
- Use `md-log` for session persistence. Without it, write through available filesystem tools; without filesystem access, return the complete Markdown record for the learner to save.

Keep optional learner context and every real state update under `workspace/`.
