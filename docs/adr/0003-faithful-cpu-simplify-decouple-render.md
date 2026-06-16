# 0003 — One faithful CPU cut: decouple render from simplify; no GPU decimation, no preview-only simplifier

The MVP-2 viewport must feel snappy on open and during slider tuning, but the
simplified preview must stay **identical to what gets exported** (issue #7,
US #25). We resolve the tension by **decoupling rendering from simplification**
rather than by making the cut cheaper-but-different: on load the GPU renders the
**original** mesh immediately (a 646k-tri static mesh is trivial to draw and
orbit — only the *collapse decision* is heavy), and the texture-preserving
quadric cut runs **async on the CPU**, swapping into the after-side when it lands.
While a cut computes, the after-side keeps the last good result dimmed with a
`teal` "simplifying…" chip, so a slow-but-honest cut reads as in-progress, never
as final.

Simplify speed is improved by removing the redundant per-cut disk re-parse (load
the OBJ into PyMeshLab once per model, re-run the collapse from the in-memory
original per target); the slider commits on release, one cut per settle.

## Considered and rejected

- **GPU-accelerated decimation.** PyMeshLab/VCGlib is CPU-only with no GPU path;
  the GPU's role here is *rendering*, not the sequential edge-collapse decision.
  Swapping to a GPU decimator would mean abandoning the texture-preserving
  quadric collapse that ADR-0002 exists to keep. Not pursued.
- **A separate lightweight preview simplifier (fast, non-texture-preserving)
  during drag.** Faster feel, but the preview would no longer equal the export —
  it would lie at the exact moment the designer judges the cut, breaking the
  faithfulness guarantee. Rejected; if a single faithful cut is still too slow on
  heavy models, the on-canvas "simplifying…" feedback covers the latency instead.
