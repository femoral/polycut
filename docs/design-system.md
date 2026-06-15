# Polycut Design System

The durable reference for **how Polycut looks, where things go, and how features are communicated to the user.** Adhere to this while implementing.

Distilled from the hi-fi prototype in `ideation/prototype/` (`Polycut.html` + `screenshots/`). The prototype is **inspiration, not specification** — it contains features that are cut or deferred (proxy export, FBX/GLB, viewport-era panels). **What** gets built is governed by the PRD and ADRs; **this document governs the visual/interaction language** of whatever is in scope.

OKLCH values below are canonical (the prototype's source of truth). QML renders sRGB, so a `Theme` singleton holds converted values; the approximate hex hints are starting points — verify against the screenshots.

---

## 1. Principles

- **Tool-like, not consumer.** Dense, efficient, low-onboarding. No marketing chrome.
- **Dark-neutral.** Dark blue-gray surfaces, minimal noise, so content (eventually the 3D viewport) is the focal point.
- **Confidence-inspiring.** Every operation reports what it did to the mesh — visible stats and feedback at each step. No mystery.
- **No dead UI.** Build only elements that have a function *today*. No purposeless decoration, and no placeholders or teasers for unbuilt features — no empty mode rails, no "coming in MVP-2" panels, no process steps for operations that don't exist yet. When a pattern in this doc lists future steps (e.g. the `IMPORT → SIMPLIFY → EXPORT` breadcrumb), render only the steps that currently exist and add the rest when they ship. A structural container the current slice will fill is fine; visible placeholder content is not.

## 2. Layout grammar

The app shell is a fixed frame:

```
┌ Top bar ───────────────────────────────────────────────────┐
│ logo + version   ·   center: filename + format   ·   win ctl │
├ rail ┬ left panel ──┬ center stage ─────┬ right inspector ───┤
│ icon │ Scene        │ Viewport /         │ stacked sections  │
│ rail │ Outliner     │ Empty state        │ (scrollable)      │
├──────┴──────────────┴────────────────────┴───────────────────┤
│ Status bar  ·····································  [Primary]    │
└──────────────────────────────────────────────────────────────┘
```

- **Top bar:** app identity + version pill at left, current filename + format tag centered, window controls at right.
- **Left:** thin vertical **icon rail**, then the **Scene Outliner** panel (object list, per-row face counts, running total at top).
- **Center stage:** the primary surface — empty-state dropzone before a model loads, the 3D viewport once it exists (post-MVP-1). Until the viewport ships, the loaded-state center is simply an empty canvas (and a working drop target) — no placeholder teaser content (see §1, "No dead UI").
- **Right inspector:** stacked, scrollable sections. **Canonical order: Simplify → Preserve → Transform → Materials.** (Only the in-scope sections render; absent sections simply don't appear.)
- **Status bar:** transient state at left, **primary action button at the far right** (e.g. "Export to SketchUp").

## 3. Color tokens (default theme: neutral hue 230 + teal accent)

| Token | OKLCH | approx sRGB | Use |
|---|---|---|---|
| `bg-0` | `0.20 0.015 230` | ~#14171a | App background |
| `bg-1` | `0.27 0.018 230` | ~#1e2226 | Panels |
| `bg-2` | `0.33 0.02 230` | ~#282d32 | Raised surfaces, inputs |
| `bg-3` | `0.40 0.02 230` | ~#343b41 | Hover / borders-as-fill |
| `fg-0` | `0.97 0.01 230` | ~#f4f6f8 | Primary text, big numbers |
| `fg-1` | `0.82 0.012 230` | ~#c4c9ce | Secondary text |
| `fg-2` | `0.62 0.015 230` | ~#8a9197 | Labels, muted |
| `fg-3` | `0.46 0.015 230` | ~#5f666c | Disabled, faint captions |
| `teal` | `0.80 0.15 190` | ~#34d3c4 | Accent: active, primary, badges |
| `teal-dim` | `0.56 0.13 190` | ~#2a8f88 | Accent pressed / track-fill |
| `coral` | `0.76 0.18 15` | ~#f76d72 | Warnings (missing texture, etc.) |
| `coral-dim` | `0.61 0.15 15` | ~#c5545b | Warning pressed |
| `hairline` | `0.95 0.01 230 / 0.10` | — | Section dividers, borders |

Alt accent themes exist in the prototype (green hue 155, purple hue 320). Default ships teal; theming is optional, not MVP-1.

## 4. Typography

- **`--font-ui` = Inter** — all labels, buttons, body. Section headers are **uppercase, letter-spaced, `fg-2`** (e.g. `SCENE OUTLINER`, `SIMPLIFY`, `PRESERVE`).
- **`--font-mono` = JetBrains Mono** — all numbers and data: face counts, the big readout (`4,240`), percentages (`−75%`), dimensions, file sizes. Numeric data is *always* mono.
- Base size ~12–13px. The hero stat (current face count) is large mono `fg-0`; its "from N original" caption is `fg-3`.

## 5. Geometry, spacing, motion

- **Radii:** `r-sm 8`, `r-md 12`, `r-lg 18`, panel radius 14.
- **Rows:** list/control row height 32–38px.
- **Spacing:** consistent `pad` (~11–16px) and `gap` (~9–13px) tokens; section gap ~14–20px.
- **Motion:** standard ease `cubic-bezier(0.22, 1, 0.36, 1)`; spring `cubic-bezier(0.34, 1.4, 0.64, 1)` for toggles/playful affordances. Keep transitions short.
- **Elevation:** layered soft shadows (`shadow-md`, `shadow-lg`) + low-alpha hairline borders. Avoid hard 1px lines.

## 6. Component patterns

- **Pill toggle** — rounded switch, `teal` when on, `bg-3` track when off; spring ease on flip.
- **Slider + badge** — horizontal track (filled portion `teal`), round handle; a live value **badge** (e.g. `−75%`) pinned near it in mono.
- **Stepper** — labeled center value with prev/next/min/max controls (used for LOD/presets).
- **Chips / tags** — small uppercase mono pills: format chips (`OBJ`), type tags (`MESH`), the reduction badge.
- **Buttons** — *primary*: filled teal (gradient), `bg-0` text, used once per context (the export action); *secondary*: outline / `bg-2` fill, `fg-1` text.
- **List row** (outliner) — name + right-aligned tag, sub-caption with mono face count; selected row = `teal` left-accent + raised `bg-2` fill.
- **Empty-state dropzone** — large centered rounded target with icon, headline ("Drop your model to begin"), format chips, and `Browse files` (primary) + `Load sample` (secondary). Dashed/glowing border.
- **Toast** — transient bottom notification for results (post-export), auto-dismiss.

## 7. Feedback & communication

- **Always show the delta.** Simplify reads `4,240 faces` with `from 16,960 original` beneath — never a bare number.
- **Status bar narrates state:** `Awaiting import` → loaded → `Selected: <object>` → export progress.
- **Process breadcrumb:** `IMPORT → SIMPLIFY → EXPORT`, current step highlighted (the prototype's `CLEAN` step maps to materials, post-MVP-1). Render only the steps that exist today — add each step when its operation ships, never as a dead placeholder (see §1, "No dead UI").
- **Warnings use `coral`,** inline next to the thing that's wrong (e.g. missing-texture flag on a material/empty state), never a blocking modal.
- **Post-export summary:** output size, face count, texture count + reveal-in-explorer.

## 8. Microcopy tone

Terse, technical, lowercase-leaning. Speak to a professional. Examples from the prototype: *"Drop your model to begin"*, *"bring the .mtl and textures along too"*, *"X faces from Y original"*, *"Awaiting import"*. No exclamation, no hand-holding.

## 9. Enforcing this in code

- A QML **`Theme` singleton** (`pragma Singleton`) holds all tokens (colors, font families, radii, spacing, durations) as properties. **Every component reads from it** — no hard-coded colors/sizes anywhere else. This is the single source of truth that keeps the system from drifting.
- Load **Inter** and **JetBrains Mono** via `FontLoader` (bundle the fonts) so rendering is identical across Windows/Mac/Linux.
- When adding any new screen, map it to §2 (where it goes) and §6 (which existing patterns it reuses) before inventing anything.
