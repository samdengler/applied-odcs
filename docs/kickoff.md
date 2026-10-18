# Kickoff for the implementation session

Run from `~/src/github.com/samdengler/applied-odcs`, on Opus 5.5:

```sh
cd ~/src/github.com/samdengler/applied-odcs
claude --model opus --add-dir ../cedar-odcs
```

`--add-dir ../cedar-odcs` lets the session edit the library repo without a
permission prompt per file.  `.claude/settings.json` pre-approves the
commands the plan uses and denies `cdk destroy` and force pushes.

Then paste this as the first message:

> Execute docs/plan.md, Work order section, steps 1 through 12, in order.
> CLAUDE.md has the conventions and the sub-agent routing.  cedar-odcs is at
> ../cedar-odcs.  You may commit and push both repos on main, tag cedar-odcs,
> create the private GitHub repo samdengler/applied-odcs, and deploy to the
> personal AWS account in us-east-1.  Take the plan's defaults instead of
> asking.  Record every default, fallback, and unverified item in
> docs/status.md.  Generate the Cognito demo password, keep it in
> .env.applied-odcs, and never commit it.  Stop after step 12 with a summary
> of what is deployed, what passed, and what fell back.

If the session must not deploy before you have looked, add: "Stop after step
6 and wait for me."
