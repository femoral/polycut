# 0008 — Auto-cluster weighs spatial Locality via an augmented colour+position feature

> Status: accepted — reversible; the connectivity-constrained approach is the escalation path.

The Auto-cluster grouped faces on **CIELAB colour alone**, with no spatial term. So spatially-separate regions of *similar* shade merged, while shade variation *within* one piece split — the k=3 lamp failed: top and base (similar dark shade) mixed across the dark ring instead of splitting into top / ring / base.

We add spatial locality by clustering on an **augmented feature `[Lab colour, λ·normalized-position]`**, with λ exposed as a **Colour ↔ Locality** slider (default a modest locality, tuned empirically on the real lamp). Position is normalized to the model's bounding box so the control is scale-invariant. Two regions of matching colour that are far apart in space — separated by a gap or an intervening Part — then split once Locality is high enough.

Chosen over **connectivity-constrained / proximity-graph clustering** (only merge spatially-connected colour clusters) because it is a tiny change to the existing k-means and hands the user a direct knob. The graph approach matches the "something in between splits it" intuition more literally but costs far more (graph build, k selection, radius tuning); it is the escalation path if the knob proves insufficient on real models.
