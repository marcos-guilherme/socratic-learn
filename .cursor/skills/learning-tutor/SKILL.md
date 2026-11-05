---
name: learning-tutor
description: Conducts diagnostic, evidence-aware mathematics and AI learning sessions. Use when the user wants to study, understand, practice, or build a learning plan for mathematics, machine learning, AI frameworks, neural networks, transformers, or related prerequisites.
---

# Learning Tutor

Before conducting a learning session, load the universal [agent entry](../../../AGENTS.md) and its canonical [pedagogy](../../../core/pedagogy.md), [session protocol](../../../core/session-protocol.md), [assessment](../../../core/assessment.md), and [evidence policy](../../../core/evidence-policy.md). Use the [mathematics map](../../../curricula/mathematics/map.md) and [AI map](../../../curricula/ai/map.md) only as needed for the learner's objective.

Map structured checks and decisions to Cursor's available question UI. If that UI is unavailable or would interrupt responsive dialogue, ask conversationally. Use web research to verify consequential volatile facts. Use Mermaid only when it makes relationships clearer than prose or an edge list.

Read optional learner context from `workspace/`. Write session records and all real learner state only under `workspace/`; never place that state in this skill or another tracked file.
