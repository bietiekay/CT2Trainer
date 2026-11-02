"""Deterministic tkinter root teardown for the native UI tests.

``tk.Tk().destroy()`` destroys the toplevel window (and every child
window, picker included) and deletes the widgets' registered Tcl
commands, but the underlying Tcl interpreter - the ``_tkinter`` Tkapp
behind ``root.tk`` - is only released when the Python ``Tk`` object is
deallocated.  The test windows form reference cycles (the ``after``
poll callback and the button commands hold bound methods inside the
interpreter; the bound methods hold the window; the ``children`` /
``master`` bookkeeping holds the root), so a destroyed root otherwise
survives until the next cyclic GC.  Cyclic GC runs on whatever thread
happens to allocate: when a worker thread's GC cycle finalizes the
interpreter, Tcl aborts the whole process with
``Tcl_AsyncDelete: async handler deleted by the wrong thread``
(observed in the 0.25 full-suite non-verbose runs, 2026-11-02: the
fault dump showed the fatal thread as a freshly started thread running
the GC collector while the main test thread was mid NASM assembly in
``test_native_record_hotkeys``).

``force_root_release`` removes the hazard: it destroys the root, drops
the named test-side references into the window stack, and forces a GC
collection on the calling thread so the interpreter is torn down on
its creator thread.

The root is passed in a one-element list (``box``) rather than
directly because the final collection must run with no Python
reference into the cycle left - not even the cleanup's argument
tuple, which unittest keeps alive while it calls the cleanup.
Clearing ``box[0]`` is what makes the cycle unreachable from inside
the cleanup itself.
"""
from __future__ import annotations

import gc

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

if tk is None:  # pragma: no cover - never executed in Tk environments
    class TclError(Exception):
        pass
else:
    TclError = tk.TclError


def force_root_release(box, clear=()):
    """Tear the root in ``box`` down on the calling (creator) thread.

    ``box`` is a one-element list holding the ``tk.Tk`` root (tests
    create it as ``[tk.Tk()]`` and keep the window in ``box[0]``).
    ``clear`` is a tuple of ``(holder, name)`` pairs: each named
    attribute (typically ``TestCase`` attributes such as ``"root"``,
    ``"window"`` or ``"app"``) is set to ``None`` before the forced
    collection, so no test-side reference keeps the root/interpreter
    cycle alive past the test.
    """
    root = box[0]
    box[0] = None
    if root is None:
        return
    try:
        root.update_idletasks()
    except TclError:
        pass
    try:
        root.destroy()
    except TclError:
        pass
    for holder, name in clear:
        if hasattr(holder, name):
            setattr(holder, name, None)
    root = None
    gc.collect()
