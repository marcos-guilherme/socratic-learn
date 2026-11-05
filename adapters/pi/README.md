# Pi Adapter

The checked-in [adapter source](skills/learning-tutor/SKILL.md) is readable in
this repository, but **do not copy it unchanged** to a project-local Pi skill:
its links have one extra directory level. The adjacent
[project-install template](skills/learning-tutor/SKILL.project.md.template) is
root-ready for the documented destination
`<project>/.pi/skills/learning-tutor/SKILL.md`.

From this repository root, install into another project with PowerShell:

```powershell
$Project = Resolve-Path "<project>"
Copy-Item AGENTS.md $Project
Copy-Item -Recurse -Force core,curricula $Project
$SkillDirectory = Join-Path $Project ".pi\skills\learning-tutor"
New-Item -ItemType Directory -Force $SkillDirectory | Out-Null
Copy-Item adapters\pi\skills\learning-tutor\SKILL.project.md.template `
  (Join-Path $SkillDirectory "SKILL.md")
```

Or with a POSIX shell:

```sh
project="<project>"
cp AGENTS.md "$project/"
cp -R core curricula "$project/"
mkdir -p "$project/.pi/skills/learning-tutor"
cp adapters/pi/skills/learning-tutor/SKILL.project.md.template \
  "$project/.pi/skills/learning-tutor/SKILL.md"
```

These commands copy the canonical files unchanged and only select a
depth-correct loader; the adapter does not duplicate their pedagogical content.
After installation, every local link in `SKILL.md` resolves against the copied
project layout.

The skill delegates to the universal [agent entry](../../AGENTS.md) and canonical [pedagogy](../../core/pedagogy.md), [session protocol](../../core/session-protocol.md), [assessment](../../core/assessment.md), and [evidence policy](../../core/evidence-policy.md). Pi extensions are optional because the skill documents a conversational or built-in fallback for each mapping.
