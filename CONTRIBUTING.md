# Contributing

`main` is the branch we deploy from, so nothing goes into it directly. Every
change gets a branch, a pull request, a green build, and a review. GitHub will
reject a push straight to `main`, including yours, including a mentor's.

## The loop

```bash
git checkout main
git pull                              # start from what's already on main
git checkout -b yourname/what-it-does # e.g. kadiri/intake-subsystem

# ... make your change, test it in sim ...

git add .
git commit -m "Add intake subsystem"
git push -u origin yourname/what-it-does
```

Then open a pull request on GitHub (it gives you a link after the push), fill
out the template, and wait for two things:

1. **The `CI` check turns green.** It builds both projects and runs the tests.
2. **Someone approves it.** Mentors are requested automatically.

Once both are done, click **Squash and merge**. Delete the branch when GitHub
offers to.

## Branch names

`yourname/what-it-does`. The slash makes branches group together in the
GitHub and VS Code branch lists, which matters once there are thirty of them.

## Before you open the pull request

Run the build yourself. It is much faster than waiting on CI, and CI runs the
exact same command:

```bash
cd "Black team"     # or cd Peashooter
./gradlew build     # gradlew.bat build on Windows
```

If that fails locally it will fail in CI. Fix it first.

## When CI is red

Open the pull request, click **Details** next to the failed check, and read the
Build job for your project. The compiler error is in there, the same one you
would see in VS Code. Push a fix to the same branch and CI runs again on its
own -- you do not need to close the pull request or open a new one.

## Reviewing someone else's pull request

Anyone can review, not just mentors. Read the diff, ask about anything you
don't follow, and check that the description says how it was tested. Approving
means you believe it is safe to put on the robot.

## The rules on `main`

| Rule | Why |
| --- | --- |
| No direct pushes | Everything gets looked at by a second person |
| Pull request must be approved | Someone besides the author agrees it's ready |
| `CI` must pass | Broken code never lands on the branch we deploy from |
| Approvals reset on a new push | An approval covers the code that was reviewed |
| No force pushes to `main` | History on `main` stays intact |

If you are stuck on something and the rules are in the way, ask a mentor. They
are not a puzzle to route around -- the branch that goes on a competition
robot is worth protecting.
