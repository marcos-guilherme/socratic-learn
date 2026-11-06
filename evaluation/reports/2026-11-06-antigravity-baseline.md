# Antigravity Semantic Baseline — 2026-11-06

## Evaluation identity
- Suite ID: 2026-11-06-antigravity-baseline
- Repository commit: da21cacf3114f932683e2f3faf50e28c5a4d35b5
- Protocol version: 1.0.0
- Protocol SHA-256: ef15b47a6feadc19834fcec4b15b35662fdfe15eb328dc16bdb6435cde8cdd8a
- Runtime: antigravity
- Runtime version: 1.5.2
- Model: claude-sonnet-5-5-high

## Scenario results
### communication-writing
- Run ID: 2026-11-06-antigravity-baseline-communication-writing
- Stop reason: infrastructure_failure
- Infrastructure failure: runtime
- Score: not assigned

### conceptual-physics
- Run ID: 2026-11-06-antigravity-baseline-conceptual-physics
- Stop reason: infrastructure_failure
- Infrastructure failure: runtime
- Score: not assigned

### practical-programming
- Run ID: 2026-11-06-antigravity-baseline-practical-programming
- Stop reason: infrastructure_failure
- Infrastructure failure: runtime
- Score: not assigned

## General findings
### headless-command-permission-block
- Classification: infrastructure
- Scenarios: conceptual-physics, practical-programming, communication-writing
- Evidence: 
- Summary: All three sessions stopped before a tutor turn because Antigravity headless mode denied the same workspace-inspection command permission.
- Research: none

## Scenario-specific findings
- None.

## Infrastructure results
- communication-writing: runtime
- conceptual-physics: runtime
- practical-programming: runtime

## Privacy statement
Raw Antigravity streams, runtime logs, provider metadata, and evaluator notes remain only under ignored .semantic-runs/. Temporary learner homes and working directories were created outside the repository and deleted after private run records were saved. This tracked report contains fictitious scenario data and the minimum sanitized excerpts needed to justify its scores.

## Baseline limitations
- communication-writing: user-home rule paths: none; above-home markers: none
- conceptual-physics: user-home rule paths: none; above-home markers: none
- practical-programming: user-home rule paths: none; above-home markers: none
User-level and above-home runtime rules were inherited with authentication; only their names were recorded, never their contents.
