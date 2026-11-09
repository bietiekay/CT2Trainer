"""Master Trainer: auto-detect running game processes and load matching tables.

The Master Trainer watches a folder of CT tables and monitors running processes.
When a matching game process is detected, the corresponding table is loaded
automatically (or the user is asked to choose if multiple tables match).

This is a convenience layer on top of the existing CT2Trainer engine — it does
not add new trainer functionality, only the folder-scan and auto-load loop.
"""

from .table_index import (
    INDEX_SCHEMA,
    INDEX_SET_SCHEMA,
    TableEntry,
    TableIndex,
    RootIndexSet,
    load_index,
    load_index_set,
    reconcile,
    save_index,
    save_index_set,
    table_key,
)
from .table_gate import (
    TableGateResult,
    TableLoadGateRefusal,
    gate_table_for_load,
)
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
from .master_state import (
    MASTER_STATE_SCHEMA,
    MASTER_STATE_FILENAME,
    MasterState,
    MasterStateRefusal,
    empty_master_state,
    load_master_state,
    save_master_state,
    master_state_from_bytes,
    master_state_to_bytes,
)
from .settings_sidecar import MasterSettingsStore, MasterSettingsRefusal
from .table_notes import (
    NOTES_DOC_NAME,
    NOTES_SCHEMA,
    NotesRefusal,
    NotesStore,
    details_note_lines,
    note_column_text,
    notes_document_from_bytes,
    notes_document_to_bytes,
    parse_tags,
)
from .table_attach import (
    ATTACH_DOC_NAME,
    ATTACH_SCHEMA,
    AttachRefusal,
    AttachStore,
    attach_document_from_bytes,
    attach_document_to_bytes,
    binding_entry,
    binding_target,
    details_attach_lines,
)
from .steamdeck_route import (
    AttachRoute,
    DeckAttachUnavailableError,
    STEAMDECK_ROUTE_TEXT,
    WINDOWS_ROUTE_TEXT,
    attach_gate,
    detect_platform,
    require_engine_attach,
    route_text,
)

__all__ = [
    "INDEX_SCHEMA",
    "INDEX_SET_SCHEMA",
    "TableEntry",
    "TableIndex",
    "RootIndexSet",
    "load_index",
    "load_index_set",
    "reconcile",
    "save_index",
    "save_index_set",
    "table_key",
    "TableGateResult",
    "TableLoadGateRefusal",
    "gate_table_for_load",
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
    "MASTER_STATE_SCHEMA",
    "MASTER_STATE_FILENAME",
    "MasterState",
    "MasterStateRefusal",
    "empty_master_state",
    "load_master_state",
    "save_master_state",
    "master_state_from_bytes",
    "master_state_to_bytes",
    "MasterSettingsStore",
    "MasterSettingsRefusal",
    "AttachRoute",
    "DeckAttachUnavailableError",
    "STEAMDECK_ROUTE_TEXT",
    "WINDOWS_ROUTE_TEXT",
    "attach_gate",
    "detect_platform",
    "require_engine_attach",
    "route_text",
]
