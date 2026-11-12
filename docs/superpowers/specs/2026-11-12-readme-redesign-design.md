# README Redesign

## Status

Approved for implementation on 2026-11-12.

## Purpose

The README should help a new learner understand Socratic Learn, see why it is
useful, and start a session without first reading the engineering history of
the project.

The current README is accurate and thorough, but its first screen gives too
much space to the terminal banner and moves into technical detail before the
reader has seen the product experience. The redesign will keep the important
facts while changing their order and presentation.

## Primary audience

The main reader is someone who wants to learn a subject with an AI agent. A
contributor or protocol author remains an important secondary reader, but
technical details should not interrupt the first-use path.

## Goals

1. Explain the learner benefit in the first screen.
2. Show a real command and a short learning exchange early.
3. Position the project for any subject, not only mathematics or AI.
4. Explain the distinction between preference, engagement, and demonstrated
   learning in plain language.
5. Preserve honest evidence language and current installation caveats.
6. Reduce the main README from about 520 lines to roughly 250 to 300 lines.
7. Sound natural and connected rather than promotional or machine-generated.

## Non-goals

1. Do not redesign the command line interface.
2. Do not create a custom image, logo, or external visual asset.
3. Do not change the learning protocol.
4. Do not advertise test counts or implementation details in the hero.
5. Do not claim that Socratic Learn guarantees mastery or works equally well
   for every learner and subject.

## Hero design

The hero uses a compact typographic presentation. The large ASCII banner stays
in the terminal and no longer dominates the README.

The first screen contains:

1. The product name.
2. The primary promise:
   "Turn any AI agent into a tutor that checks whether you actually learned."
3. A short sentence that includes the phrase "learn any subject" and gives a
   few varied examples.
4. Three product-level signals:
   any subject, the learner's preferred AI host, and progress through
   application.
5. The command `socratic "I want to learn..."`.
6. A direct link to installation.

Technical badges may show the supported Python version and license, but test
counts, build mechanics, and protocol version numbers do not belong in this
area.

## Information architecture

The README follows this order:

1. **See a session** presents a short, realistic exchange.
2. **Why it is different** explains adaptive support, application evidence,
   resumability, and preference-aware delivery.
3. **Quick start** gives installation and the first command.
4. **Choose an AI host** explains the roles of Socratic Learn, Pi,
   Antigravity, and Claude without treating them as equivalent products.
5. **Learn from an article** introduces `socratic read` and its evidence
   boundaries.
6. **How the method works** gives the compact protocol flow.
7. **Research and limitations** explains what informed the design and what has
   not yet been established.
8. **Technical documentation** links to installation, adapters, security,
   evaluation, and contribution material.

Detailed installation recovery, source ingestion limits, migration behavior,
and contributor commands should move to their existing dedicated documents
when a link can preserve the same information. Short safety and availability
caveats stay in the README where they affect a user's immediate decision.

## Writing rules

The prose uses ordinary English, active voice, and connected paragraphs.

The README must:

1. Avoid em dashes and en dashes.
2. Avoid unusual words when a common word is precise.
3. Avoid slogan stacks and unsupported superlatives.
4. Avoid repeated contrast formulas such as "not X, but Y."
5. Avoid making every sentence a bullet or a separate fragment.
6. Use headings and lists only when they improve scanning.
7. Lead each section into the next with a clear reason.
8. Define the role of each product name when it first appears.
9. Keep scientific and technical caveats close to the claims they qualify.

## Evidence language

The README separates:

1. what learners report preferring;
2. what may improve participation or continued use;
3. what observed application, retrieval, or transfer can show.

A preferred format may change presentation and pace. It does not establish a
fixed learning style or prove mastery. Confidence, completion, chat length,
and activity count remain outside the mastery claim.

Research references should support specific design decisions. The text must
state that the cited studies evaluate their own settings and do not validate
Socratic Learn as a whole.

## Technical constraints

The redesign must preserve:

1. exact versioned installation URLs and release availability wording;
2. source reading commands and safety boundaries;
3. the privacy promise for learner records;
4. the POSIX same-user threat model summary or a clear linked summary that
   satisfies the repository safety contract;
5. universal subject positioning;
6. the personal project narrative;
7. the compact protocol flow;
8. all links needed for users to find details removed from the main page.

README validators should protect claims, safety, onboarding, and required
links. They should not force the old presentation order or require the
terminal ASCII banner in the README. The CLI banner remains independently
tested.

## Verification

Implementation is complete when:

1. the README follows the approved order;
2. the first screen contains the promise, learner signals, command, and
   installation link;
3. test counts do not appear in the hero;
4. the ASCII banner remains in the CLI but is not required in the README;
5. all Markdown links resolve;
6. the repository validator passes;
7. the complete test suite passes;
8. the README contains no em dash or en dash characters;
9. a final prose review finds no abrupt transitions, repetitive sentence
   templates, vague adjectives, synthetic slogan patterns, or claims without
   nearby qualification.

## Final human-style review

The last pass reads the README from top to bottom as a new visitor. It checks
whether each paragraph answers the question raised by the previous one, whether
the command arrives before implementation detail, and whether technical terms
are introduced only when needed.

A separate pattern scan checks for overly regular sentence length, excessive
bold text, repeated three-item lists, repeated "not X, but Y" constructions,
marketing filler, translation-like wording, and compressed fragments that
sound synthetic rather than conversational.
