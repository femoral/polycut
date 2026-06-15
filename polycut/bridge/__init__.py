"""Qt bridge — the thin seam between the QML layer and the headless core.

Only this layer imports Qt. It exposes the core pipeline to QML as a single
``processor`` object (properties for stats, slots for load/export, signals for
results), and never the other way around.
"""

from polycut.bridge.processor import Processor

__all__ = ["Processor"]
