# Universal Learning Positioning — Design

## Goal

Position Socratic Learn as a portable, evidence-aware protocol for learning
any subject or skill. Mathematics and AI remain useful starter curricula and
examples of rigorous application, but they must not appear to define the
product boundary.

## Public promise

The canonical tagline is:

> A portable, evidence-aware Socratic protocol for learning anything.

The opening description must explain that compatible AI agents can apply the
same learning method to conceptual subjects, practical skills, technical
domains, and interdisciplinary goals. Mathematics and AI should appear only
after this universal promise, as included examples and starter curricula.

The claim "learning anything" describes the protocol's intended domain. It
does not claim that every host model already knows every subject, that every
topic has a bundled curriculum, or that use guarantees mastery.

## Positioning hierarchy

Public descriptions should follow this order:

1. Socratic Learn is for any subject or skill.
2. It uses observable outcomes, prerequisite diagnosis, a learner-approved
   dependency path, adaptive dialogue, application, and evidence-based
   closure.
3. Mathematics and AI are the first bundled curriculum maps.
4. Host capabilities and subject knowledge still determine what an agent can
   reliably teach or verify.

## Surfaces to update

The universal position must be consistent across:

- the README tagline, opening paragraphs, example goals, and limitations;
- the GitHub repository description and discovery topics;
- Cursor and Pi skill metadata;
- adapter documentation;
- public installation and manifest documentation where product scope is
  described;
- repository validation tests that protect the public positioning.

Historical design documents and implementation plans remain unchanged except
for optional pointers to this newer positioning decision. Their old wording
records the scope approved at the time and is not current marketing copy.

## Pedagogy and curricula

The four canonical protocol documents remain the behavioral core. Their
general learning process already applies beyond mathematics and AI. Any
domain-specific guidance must be framed as conditional specialization rather
than a universal requirement.

The existing mathematics and AI maps remain bundled and unchanged in
structure. No new curriculum is required for this positioning change. Future
curricula may be added independently without changing the core protocol.

## Compatibility and distribution

This is a positioning and discoverability change, not a package or schema
change. It must not alter:

- the `socratic_learn` package or command;
- installation paths, receipts, migration behavior, or manifest schema;
- deterministic bundle construction;
- supported adapters or security guarantees.

The generated prompt may change only when canonical source wording changes.
Any generated change must be rebuilt deterministically and pass repository
validation.

## Acceptance criteria

The change is complete when:

- the primary public promise clearly says Socratic Learn can support learning
  any subject or skill;
- no current product description presents mathematics and AI as the product's
  boundary;
- mathematics and AI are consistently described as starter curricula or
  examples;
- limitations distinguish universal protocol scope from host knowledge,
  curriculum coverage, and learning guarantees;
- validator coverage prevents the README and skill metadata from regressing
  to mathematics-and-AI-only positioning;
- local tests, deterministic build validation, and the hosted Windows,
  Ubuntu, and macOS matrix pass.
