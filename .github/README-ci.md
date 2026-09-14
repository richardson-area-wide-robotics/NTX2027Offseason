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

## When a build fails and the code is fine

The first push to `main` failed on both projects with
`java.net.SocketTimeoutException: Read timed out`, thrown from
`org.gradle.wrapper.Install`. That is not the robot code — that is the Gradle
*wrapper* failing to download Gradle itself from `services.gradle.org`. A plain
re-run went green with no change.

Two things made that likely, and both are fixed now:

- The distribution was re-downloaded on every job. `setup-java`'s gradle cache
  covers `~/.gradle/caches` and `~/.gradle/wrapper`, but WPILib's wrapper sets
  `distributionPath=permwrapper/dists`, so ~100 MB came down fresh every time —
  twice per run, once per project. The "Cache the Gradle distribution" step
  covers that path now.
- `networkTimeout` in `gradle-wrapper.properties` was 10 s, which is tight for a
  100 MB download. It is 60 s now, in both projects. This also helps students
  building for the first time on school wifi.

If a build still fails somewhere in `org.gradle.wrapper` or on a `Could not
resolve` against `frcmaven.wpi.edu`, it is upstream and a re-run is the right
response. A failure in `> Task :compileJava` is real and belongs to whoever
pushed.

## Adding a project

Add it to the matrix in `build.yml`:

```yaml
- project: New Robot Folder
  slug: new-robot-folder
```

Nothing else changes — `CI` covers it automatically, and branch protection needs
no edit.

## The rules on `main`

Two rulesets are applied to `main`, and the JSON for both lives here so changes
to them get reviewed like code.

| File | ID | What it does | Who can bypass |
| --- | --- | --- | --- |
| [`rulesets/protect-main-build.json`](rulesets/protect-main-build.json) | 23315767 | `CI` must pass; no force pushes; `main` can't be deleted | **Nobody** |
| [`rulesets/protect-main-review.json`](rulesets/protect-main-review.json) | 23315816 | Pull request required, 1 approval, approvals dismissed on a new push | The four mentors |

They are split because a ruleset's bypass list is all-or-nothing — a bypass
actor skips every rule in that ruleset. Splitting them is what lets a mentor
merge their own pull request without waiting for an approval while the build
gate still applies to them. Put the two rule sets in one ruleset and a mentor
bypass would skip `CI` too.

Note what the split does *not* allow: a mentor still cannot push straight to
`main`, because a freshly pushed commit has no passing `CI` run and the build
ruleset has no bypass. Mentors can merge unreviewed; nobody can merge unbuilt.

To re-apply after editing a file:

```bash
# update in place -- keeps the ID, which is what you almost always want
gh api --method PUT repos/richardson-area-wide-robotics/NTX2027Offseason/rulesets/23315767 \
  --input .github/rulesets/protect-main-build.json
```

`POST` to `.../rulesets` (no ID) creates a new one instead. `gh api
repos/richardson-area-wide-robotics/NTX2027Offseason/rulesets` lists what
exists, and `gh api repos/.../rules/branches/main` shows what is actually in
force on the branch.

These are *rulesets*, not classic branch protection, because classic protection
lets repository admins push straight through by default.

### The gap worth knowing about

A repo admin can delete or disable a repo-level ruleset, so admin is the real
perimeter here, not the rules.

There were nine admins on 2026-09-14, one of them a student. That student is now
`write`, which was the only repo-level grant of admin in the list. **The other
eight are organization owners**, and an org owner has admin on every repository
in the org by definition — a repo-level permission change cannot reduce them.
Checked, not assumed: the set of remaining repo admins and the set of org owners
are identical.

So the honest statement of what these rules do: they stop an accident, and they
stop anyone with `write` — which is everyone except the eight owners. They do not
constrain an org owner.

Narrowing it further is an org-level decision, not a repo one:

- change who is an **organization owner** (Settings → People → Role at the org).
  That affects every repo the org has, so it isn't a CI question.
- move both rulesets to the **organization** level (Settings → Rules at the org,
  or `POST /orgs/{org}/rulesets`). The same JSON works, with `conditions` widened
  to name the repositories it covers. This doesn't shrink the owner list, but it
  does mean nobody can quietly remove the rules from one repo.

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
