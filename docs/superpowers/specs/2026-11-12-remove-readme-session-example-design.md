# Remove README Session Example Design

## Goal

Preserve curiosity in the project introduction by removing the complete
`See a session` example from the root README.

## Scope

Delete the `## See a session` heading, its introductory paragraph, the example
dialogue, and its closing explanation. Do not replace them with a teaser,
summary, collapsed block, or other copy.

After the change, the opening material and badges lead directly into
`## Why it is different`. All other README content remains unchanged.

## Verification

Extend the existing README contract test to confirm that the removed heading
and dialogue markers are absent and that `## Why it is different` remains
after the installation link and badges.

Repository validation and whitespace checks must pass before the change is
committed.
