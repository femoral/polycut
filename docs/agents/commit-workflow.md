# Commit workflow

How work lands in this repo. The orchestrator (the main agent) drives it.

## Rules

- **One issue at a time.** Work a single GitHub issue start to finish before picking up the next.
- **One commit per issue.** Squash the issue's work into a single commit. The commit message references the issue (e.g. `… (#42)` or `Closes #42`).
- **Push directly to `master`.** No branches, no pull requests.

## Pre-commit guards (mandatory)

Before **every** commit, the orchestrator runs both guard subagents on the changes about to be committed. Run them in parallel.

1. **`privacy-guard`** — no leaked PII, secrets, or machine/environment details (absolute paths, hostnames, IPs, configs outside the project). See `.claude/agents/privacy-guard.md`.
2. **`design-system-guard`** — changes conform to `docs/design-system.md`. See `.claude/agents/design-system-guard.md`.

Both run on Sonnet, are **advisory and read-only** (they report; they never edit or commit), and each returns:

```
DECISION: PASS | FAIL
FINDINGS:
- ...
```

## Decision flow

- **Both PASS** → the orchestrator stages the issue's changes, commits (one commit, referencing the issue), and pushes to `master`.
- **Either FAILS** → the orchestrator does **not** commit. It relays each guard's `FINDINGS` to the user and asks whether to (a) apply the suggested fixes and re-run the guards, or (b) proceed anyway. The user decides; only commit on the user's go-ahead.

The orchestrator never overrides a FAIL on its own — the call to proceed is always the user's.

## Sequence

```
pick issue → implement → stage changes
           → run privacy-guard + design-system-guard (parallel)
           → both PASS ? commit + push to master
                       : report findings → user decides
           → close issue
```
