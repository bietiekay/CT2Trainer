#!/usr/bin/env python3
"""AP-10 corpus denominator tool (CT2Trainer edition).

Self-contained, stdlib-only, read-only static inventory and gap analysis for a
Cheat Engine .CT corpus (13 pinned start tables + remaining corpus). Produces
deterministic ``inventory.json`` and ``gap-report.json`` artifacts with the
same schema as the committed reference artifacts under ``gap_inventory/``.

Classification logic is ported unchanged from an early development run;
only imports were adjusted to package form. CT Lua/AA bodies are never
executed.
"""

__version__ = "1.0.0"

SCHEMA_NAME = "corpus-denominator/v1"

__all__ = ["SCHEMA_NAME", "__version__"]
