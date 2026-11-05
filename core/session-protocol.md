# Session Protocol

## Inputs

Accept a learner objective and any optional files supplied under `workspace/`.
Read an available learner profile and progress record before questioning, but
do not assume they are current. Keep real learner data under `workspace/` and
out of version control. If the objective is vague, clarify it before diagnosis.

## 1. Define an observable outcome

Convert the objective into a performance that can be observed in this session:
an explanation, derivation, prediction, solution, implementation, or diagnosis
under stated conditions. Confirm the outcome and its completion evidence with
the learner.

## 2. Diagnose relevant prerequisites

Inspect only prerequisites that could block the outcome. Use the assessment
protocol to bracket the learner's knowledge edge. The default budget is six
questions; the learner may request fewer or more. Stop early when the evidence
is sufficient to propose a path.

## 3. Present and approve a dependency path

Present the observable outcome, ordered dependency nodes, already demonstrated
foundations, gaps to address, and completion criterion. Explain every edge and
exclude unrelated branches. Do not begin teaching until the learner approves
or adjusts the path.

## 4. Teach one node at a time

For each approved node, state why it is needed now, connect or derive it from
demonstrated foundations, and request an active application. After an error,
target the mistaken assumption and provide a new attempt. After success,
increase difficulty or test transfer rather than repeating an equivalent item.
Re-plan and seek approval if a newly discovered gap changes the path.

## 5. Close and persist

Close with the outcome, the approved path traversed, observable evidence,
remaining gaps, unresolved uncertainty, and one next step. When filesystem
access exists, update the applicable private records under `workspace/`.
Otherwise return a Markdown record ready for the learner to save. Never place
real learner data in tracked repository files.

## Capability fallbacks

- Without structured quiz support, ask one question at a time in conversation.
- Without web access, mark volatile claims unverified and prefer stable content.
- Without subagents or parallel work, research and teach sequentially.
- Without diagram rendering, use Mermaid if available or a textual edge list.
- Without filesystem access, return the complete session record as Markdown.
- Without cross-session memory, ask for a prior summary and state what is unknown.

An unavailable capability changes the medium, not the learning protocol.

## Session record contract

Persist or return one record with exactly these shared headings:

```markdown
# Session Record
## Observable outcome
## Approved dependency path
## Evidence demonstrated
## Remaining gaps and uncertainty
## Next step
```

Under the dependency heading, record ordered nodes and explicit edges. Under
evidence, record learner actions and results rather than self-reported mastery.
State when no evidence was collected or a claim remains unverified.
