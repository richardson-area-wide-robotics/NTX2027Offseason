# CI and branch protection

Notes for mentors and leads. Students want [CONTRIBUTING.md](../CONTRIBUTING.md).

## What runs

[`workflows/build.yml`](workflows/build.yml) builds every project in the repo on
each pull request into `main` and on each push to `main`. It runs the same
`./gradlew build` a student runs locally, which compiles the code and runs the
JUnit tests.

The matrix produces one job per project — `Build (Black team)`,
`Build (Peashooter)` — and then a single `CI` job that passes only if all of
them passed.

**Branch protection requires `CI`, not the individual `Build` jobs.** Matrix job
names change the moment a project is added or renamed, and a required check that
no longer exists blocks every pull request forever while looking like it is
just "pending". The `CI` name never changes.

## Adding a project

Add it to the matrix in `build.yml`:

```yaml
- project: New Robot Folder
  slug: new-robot-folder
```

Nothing else changes — `CI` covers it automatically, and branch protection needs
no edit.

## The rules on `main`

[`rulesets/protect-main.json`](rulesets/protect-main.json) is the ruleset applied
to `main`, kept here so changes to it get reviewed like code. To re-apply it
after an edit:

```bash
gh api --method POST repos/richardson-area-wide-robotics/NTX2027Offseason/rulesets \
  --input .github/rulesets/protect-main.json
```

To update an existing one, `PUT` to `.../rulesets/{id}` instead. `gh api
repos/richardson-area-wide-robotics/NTX2027Offseason/rulesets` lists the IDs.

It is a *ruleset*, not classic branch protection, because classic protection
lets repository admins push straight through by default. A ruleset applies to
everyone unless a bypass actor is named, and right now none is.

### The gap worth knowing about

Nine people have **admin** on this repo, and a repo admin can delete or disable a
repo-level ruleset. One of them is on the students team. So this stops an
accidental push to `main`; it does not stop someone who decides to go around it.

Closing that properly is one of:

- drop the admins who don't need admin down to write, or
- move the ruleset to the organization level, where only org owners can change
  it (Settings → Rules at the org, or `POST /orgs/{org}/rulesets`).

## Where this is going

Deliberately minimal for now — a build gate that can't produce false failures is
worth more than a thorough one students learn to ignore. The next steps, roughly
in order:

1. **Formatting** — WPILib uses [Spotless](https://github.com/diffplug/spotless).
   Run the formatter across both projects in one commit first, then add
   `spotlessCheck` to the build, or every pull request drowns in whitespace.
2. **Linting** — ErrorProne or NullAway on top of the compile.
3. **Real tests** — there are none yet. `src/test/java` with JUnit 5 is already
   wired up in `build.gradle`; simulation-based tests of a subsystem are the
   useful kind here.
4. **Self-healing** — a `format` job that pushes a formatting fix back to the
   pull request branch, and Dependabot for the Gradle wrapper and vendordeps.

## Dead files

Each project still carries a `.github/workflows/classroom.yml` left over from
GitHub Classroom. GitHub only reads workflows from the repo root, so those never
run. They're harmless; they're also confusing to a student who finds one and
assumes it is the build. Worth deleting.
