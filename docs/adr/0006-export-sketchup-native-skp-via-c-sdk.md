# 0006 — "Export to SketchUp" writes native .skp via the SketchUp C SDK (supersedes 0001)

> Status: accepted — supersedes ADR-0001.

ADR-0001 made `.dae` the SketchUp export because native `.skp` needs the proprietary SketchUp C++ SDK (no clean Python binding), and SketchUp **Pro** imports `.dae` with full fidelity. A new constraint overturns that premise: Polycut now also targets users on **SketchUp Free (Web)**, whose import is restricted to `.skp`, `.png`, and `.jpg` — `.dae` and `.obj` import are paywalled behind the Go/Pro tiers. So a Free-Web user cannot consume a `.dae` or `.obj` at all; **native `.skp` is the only door into the free tier.**

We therefore make "Export to SketchUp" write a native `.skp` by `ctypes`-wrapping the SketchUp C API runtime DLL (`SketchUpAPI`), bundled with the Windows build. Each Part becomes a named **Group** with its own material slot, the baked texture **embedded** in the `.skp` (self-contained, unlike the DAE's sibling image), and the Transform (scale + up-axis) and units baked in — mirroring the per-Part structure of the DAE writer. `.dae` is demoted to a **generic interchange** format alongside GLB and OBJ; it is no longer framed as "Export to SketchUp".

## Licensing

Polycut is GPLv3 and the SDK is proprietary. As sole copyright holder we add a **GPLv3 linking exception** covering the SketchUp SDK, contingent on **verifying the SDK EULA permits redistributing its runtime DLLs** inside a third-party app. Both are prerequisites to shipping; the spike resolves them before code lands.

## Platform

The SDK ships only for Windows and Mac (no Linux build), so SKP is a **platform-gated backend**: feature-detected at runtime and hidden/disabled where the DLL can't load. Primary dev/test is a **local Windows VM** (the ship target), validated by an SDK **write→readback round-trip** (assert Part/material/face counts; needs no SketchUp install) plus a **SketchUp Free (Web) open** as the empirical acceptance gate. `.dae` remains the cross-platform fallback and the only SketchUp-fidelity export testable in the Linux/Nix loop.

## Considered and rejected

- **DAE as the SketchUp export (ADR-0001).** Free Web can't import it — paywalled. Kept only as generic interop.
- **Ruby API driving a headless SketchUp install.** Needs SketchUp present on the machine, not bundle-able; defeats the free-alternative goal.
- **Don't bundle the DLL (user installs the SDK).** Sidesteps the GPL linking question via aggregation, but a worse default UX; rejected for the shipped path.
- **Relicense Polycut away from GPL.** Too broad a change to make for one feature.

## Consequences

- SKP exists only on Windows; on Linux/dev the SketchUp export is absent and only generic interop (DAE/GLB/OBJ) is offered.
- The `.skp` format version must target what SketchUp Free (Web) actually opens — verified empirically in the spike, not assumed.
