# Pi Adapter

The checked-in [adapter source](skills/learning-tutor/SKILL.md) is readable in
this repository, but **do not copy it unchanged** to a project-local Pi skill:
its links have one extra directory level. The adjacent
[project-install template](skills/learning-tutor/SKILL.project.md.template) is
root-ready for the documented destination
`<project>/.pi/skills/learning-tutor/SKILL.md`.

The installation is namespaced and fail-closed: it creates the canonical
package at `<project>/.learning-tutor/` and aborts if that directory or the Pi
skill file already exists. It does not write to `<project>/AGENTS.md`.

From this repository root, install with PowerShell:

```powershell
$Project = Resolve-Path "<project>"
$PackageDirectory = Join-Path $Project ".learning-tutor"
$SkillDirectory = Join-Path $Project ".pi\skills\learning-tutor"
$SkillFile = Join-Path $SkillDirectory "SKILL.md"
if (Test-Path $PackageDirectory) {
  throw "Installation aborted: $PackageDirectory already exists."
}
if (Test-Path $SkillFile) {
  throw "Installation aborted: $SkillFile already exists."
}
New-Item -ItemType Directory $PackageDirectory | Out-Null
Copy-Item AGENTS.md $PackageDirectory
Copy-Item -Recurse core,curricula $PackageDirectory
New-Item -ItemType Directory -Force $SkillDirectory | Out-Null
Copy-Item adapters\pi\skills\learning-tutor\SKILL.project.md.template `
  $SkillFile
```

Or with a POSIX shell:

```sh
project="<project>"
package_dir="$project/.learning-tutor"
skill_file="$project/.pi/skills/learning-tutor/SKILL.md"
if [ -e "$package_dir" ]; then
  echo "Installation aborted: $package_dir already exists." >&2
  exit 1
fi
if [ -e "$skill_file" ]; then
  echo "Installation aborted: $skill_file already exists." >&2
  exit 1
fi
mkdir "$package_dir"
cp AGENTS.md "$package_dir/"
cp -R core curricula "$package_dir/"
mkdir -p "$project/.pi/skills/learning-tutor"
cp adapters/pi/skills/learning-tutor/SKILL.project.md.template \
  "$skill_file"
```

The adapter skill contains only loader and capability-mapping guidance; the
pedagogical source remains in the namespaced canonical package.

## Project agent integration

The installer does not overwrite or edit the project's `AGENTS.md`. If the
project already has one, manually add a short pointer such as:

```markdown
Before a learning session, read the namespaced
[learning tutor entry](.learning-tutor/AGENTS.md).
```

If the project has no `AGENTS.md`, you may create one containing that same
short loader. This integration is explicit and separate from installation.

The skill delegates to the universal [agent entry](../../AGENTS.md) and canonical [pedagogy](../../core/pedagogy.md), [session protocol](../../core/session-protocol.md), [assessment](../../core/assessment.md), and [evidence policy](../../core/evidence-policy.md). Pi extensions are optional because the skill documents a conversational or built-in fallback for each mapping.
