"""Master Trainer: auto-detect running game processes and load matching tables.

The Master Trainer watches a folder of CT tables and monitors running processes.
When a matching game process is detected, the corresponding table is loaded
automatically (or the user is asked to choose if multiple tables match).

This is a convenience layer on top of the existing CT2Trainer engine — it does
not add new trainer functionality, only the folder-scan and auto-load loop.
"""

from .table_index import TableEntry, TableIndex, load_index, reconcile, save_index
from .process_watch import (
    ProcessSnapshotEntry,
    ProcessLister,
    ProcfsProcessLister,
    WindowsProcessLister,
    default_process_lister,
    match_targets,
    names_match,
)
from .orchestrator import (
    MasterOrchestrator,
    LoadOutcome,
    PendingChoice,
    TickOutcome,
    STATE_ACTIVE,
    STATE_CHOOSING,
    STATE_LOADING,
    STATE_WAITING,
)
from .master_ui import MasterWindow, MasterApp, run_master

__all__ = [
    "TableEntry",
    "TableIndex",
    "load_index",
    "reconcile",
    "save_index",
    "ProcessSnapshotEntry",
    "ProcessLister",
    "ProcfsProcessLister",
    "WindowsProcessLister",
    "default_process_lister",
    "match_targets",
    "names_match",
    "MasterOrchestrator",
    "LoadOutcome",
    "PendingChoice",
    "TickOutcome",
    "STATE_ACTIVE",
    "STATE_CHOOSING",
    "STATE_LOADING",
    "STATE_WAITING",
    "MasterWindow",
    "MasterApp",
    "run_master",
]
