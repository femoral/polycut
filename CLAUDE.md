# polycut

## Dev environment (NixOS)

`shell.nix` provides the native libraries PySide6/Qt (incl. QtQuick3D) and pymeshlab dlopen at runtime, and points Qt at the hardware GL driver so the viewport runs on the GPU (not the llvmpipe software fallback). Python deps live in a local `.venv` (wheels); the shell prepends `.venv/bin` to `PATH`.

```
nix-shell                                           # enter the dev shell
python -m venv .venv && pip install -e '.[gui,dev]' # one-time, inside the shell
python -m polycut.app                               # launch the GUI on the GPU
QT_QPA_PLATFORM=offscreen pytest -q -m "not slow"   # run the suite headless
```

Tests must run `offscreen` (no display); the GUI defaults to the `xcb` backend (override `QT_QPA_PLATFORM=wayland` for a native Wayland window). Drop `-m "not slow"` to include the 646k-face Meshy fixture end-to-end.

## Commit workflow

One issue at a time, one commit per issue, pushed directly to `master` (no PRs). Before **every** commit the orchestrator runs two read-only Sonnet guard subagents on the staged changes — `privacy-guard` (no leaked PII/secrets/machine details) and `design-system-guard` (conforms to `docs/design-system.md`). Both PASS → commit + push. Either FAILS → relay findings, user decides. See `docs/agents/commit-workflow.md`.

## Agent skills

### Issue tracker

Issues and PRDs live as GitHub issues in `femoral/polycut`, managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage roles, each mapped to its identically-named label string (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
