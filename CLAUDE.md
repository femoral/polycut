# polycut

## Commit workflow

One issue at a time, one commit per issue, pushed directly to `master` (no PRs). Before **every** commit the orchestrator runs two read-only Sonnet guard subagents on the staged changes — `privacy-guard` (no leaked PII/secrets/machine details) and `design-system-guard` (conforms to `docs/design-system.md`). Both PASS → commit + push. Either FAILS → relay findings, user decides. See `docs/agents/commit-workflow.md`.

## Agent skills

### Issue tracker

Issues and PRDs live as GitHub issues in `femoral/polycut`, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles, each mapped to its identically-named label string (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
