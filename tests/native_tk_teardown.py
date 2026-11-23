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

RT-7 (0.52.2 lane): ``destroy()`` only releases the interpreter
commands tracked in a widget's ``_tclCommands`` list.  Callbacks
registered outside that bookkeeping pin the whole C interpreter: the
interpreter holds the callback, the callback holds the root, the root
holds the interpreter wrapper - a C-mediated cycle Python's collector
cannot see.  The variable that owns such a command is never collected
while that C reference exists (the trainer's search-field ``StringVar``
trace goes through ``Variable._register``, whose entry is only cleared
in ``Variable.__del__``).  Proven 2026-11-23 against the exact leaking
test (``SessionHotkeyUiTests``): after a completed ``destroy()``
(``_tclCommands`` cleared, children empty, no ``TclError``) one
CallWrapper holding the root survived with a LIVE interpreter.  The
mechanism was then pinned further (same day, diagnostics v21-v25):
EVERY Python-registered command entry - even one whose callback is a
plain module function referencing nothing else - holds a strong
reference to the app in C memory (a bare root with one surviving
``createcommand`` entry measures app refcount 3 instead of the free
baseline 2, and only ``deletecommand`` releases it), and the trace
entry is the single C-table survivor after ``destroy()`` because its
name is tracked in the ``StringVar``'s ``_tclCommands`` list, not the
root's.  ``force_root_release`` therefore runs the production
equivalent of the trainer's ``release_search_trace()`` generically:
for every live ``tkinter.Variable`` bound to the app being torn down
it mimics ``Variable.__del__`` (Tcl unset + ``deletecommand`` for
every registered name) so the C table cannot outlive the root.  It
then verifies - via a weakref - that the root was actually reclaimed,
and, if not, drops every Python handle to the interpreter (``root.tk``
and each widget's / variable's shared ``tk`` / ``_tk`` reference),
lets the C interpreter dealloc and release every registered callback,
and collects again.  A root that survives even that is a named,
fail-closed teardown refusal that names the surviving holders - a
silent leak would leave a live interpreter for a later cyclic GC on a
foreign thread (the ``Tcl_AsyncDelete`` fatal race this module exists
to prevent).
"""
from __future__ import annotations

import gc
import os
import weakref

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

if tk is None:  # pragma: no cover - never executed in Tk environments
    class TclError(Exception):
        pass
else:
    TclError = tk.TclError


def release_master_analysis_workers():
    """Stop every live Master-Trainer plan-analysis worker.

    MT-24 (0.32): window tests build the waiting view (which starts
    the background ``AnalysisWorker``) but never call ``close()``.  A
    leaked worker thread keeps doing plan-compiles (and its
    allocations run cyclic GC on a foreign thread - the same
    wrong-thread finalization hazard this module exists to avoid,
    cf. the 0.25 fault dump) and destabilizes later tests in the
    same process.  ``stop()`` is idempotent and bounded, so calling
    this from every Tk teardown is safe; non-Master tests find no
    live workers and it is a no-op.
    """
    try:
        from ct2trainer.native.master_trainer.analysis_worker import (
            active_workers)
    except ImportError:
        return
    for worker in active_workers():
        try:
            worker.stop()
        except Exception:
            pass


def _release_variable_traces(app):
    """Mimic ``Variable.__del__`` for every live ``tkinter.Variable``
    bound to the app about to be torn down.

    ``Variable._register`` puts the trace callback in the app's C
    command table (``createcommand``) and records the name only in
    the variable's own ``_tclCommands`` list - so a ``destroy()`` of
    the root never deletes it, and the variable is never collected
    while the C reference exists (the C reference keeps the
    app -> CallWrapper -> root -> app cycle alive, and the cycle
    crosses the GC-untracked ``tkapp`` object, so the cyclic
    collector never sees it).  Proven 2026-11-23 (diagnostics
    v21-v25): the trace entry is the single C-table survivor after
    ``destroy()`` and holds one strong app reference that only
    ``deletecommand`` releases.  The production path covers this
    through ``TrainerWindow.release_search_trace()`` inside
    ``close()``; tests that tear down the root directly (without a
    ``close()``) need this equivalent here so no interpreter
    command can outlive the root.
    """
    variable = getattr(tk, "Variable", None)
    if app is None or variable is None:
        return
    for obj in gc.get_objects():
        if not isinstance(obj, variable):
            continue
        if getattr(obj, "_tk", None) is not app:
            continue
        names = getattr(obj, "_tclCommands", None)
        try:
            name = getattr(obj, "_name", None)
            if name is not None and app.getboolean(
                    app.call("info", "exists", name)):
                app.globalunsetvar(name)
        except Exception:
            pass
        for name in names or ():
            try:
                app.deletecommand(name)
            except Exception:
                pass
        try:
            obj._tclCommands = None
        except Exception:
            pass


def _drop_interpreter_and_collect(watch):
    """Drop every Python handle to the root's Tcl interpreter and
    collect; True when the root is reclaimable afterwards.

    ``watch`` is a ``weakref.ref`` of the destroyed root.  The
    interpreter (the C ``_tkinter`` object behind ``root.tk``) is
    shared by the root, every widget (``widget.tk``) and every
    variable (``variable._tk``); dropping every handle is what lets
    the C dealloc run and release the interpreter command table - the
    only way to break a retention whose reference crosses into C
    memory (invisible to the collector).  No local of this function
    may keep the interpreter - or any member of the cycle - alive
    across the final collection: a lingering ``app`` local would re-pin
    the exact retention this backstop exists to break (verified
    2026-11-23: the first backstop revision kept ``root.tk`` in a
    local and the C dealloc never ran).
    """
    root = watch()
    if root is None:
        return True
    app = root.tk
    if app is not None:
        for obj in gc.get_objects():
            for attr in ("tk", "_tk"):
                try:
                    if getattr(obj, attr, None) is app:
                        setattr(obj, attr, None)
                except Exception:
                    pass
        obj = None
    app = None
    root = None
    gc.collect()
    return watch() is None


def _describe_holders(watch):
    """Name the Python references keeping the destroyed root alive."""
    root = watch()
    if root is None:
        return []
    here = os.path.basename(__file__)
    desc = []
    for ref in gc.get_referrers(root):
        t = type(ref)
        tn = t.__name__
        if tn == "frame":
            if ref.f_code.co_filename.split(os.sep)[-1] == here:
                continue
            names = [k for k, v in list(ref.f_locals.items()) if v is root]
            desc.append("frame %s::%s locals=%r" % (
                ref.f_code.co_filename.split(os.sep)[-1],
                ref.f_code.co_name, names))
        elif tn == "dict":
            keys = [k for k, v in ref.items() if v is root]
            desc.append("dict %r" % keys[:8])
        elif tn in ("list", "tuple"):
            try:
                desc.append("%s[%d]" % (tn, ref.index(root)))
            except ValueError:
                desc.append(tn)
        elif hasattr(ref, "__name__"):
            desc.append("%s(%s)" % (tn, ref.__name__))
        else:
            desc.append(tn)
    root = None
    return desc


def force_root_release(box, clear=()):
    """Tear the root in ``box`` down on the calling (creator) thread.

    ``box`` is a one-element list holding the ``tk.Tk`` root (tests
    create it as ``[tk.Tk()]`` and keep the window in ``box[0]``).
    ``clear`` is a tuple of ``(holder, name)`` pairs: each named
    attribute (typically ``TestCase`` attributes such as ``"root"``,
    ``"window"`` or ``"app"``) is set to ``None`` before the forced
    collection, so no test-side reference keeps the root/interpreter
    cycle alive past the test.

    The RT-7 backstop (module docstring) verifies the release via a
    weakref and, for a root still pinned by an untracked interpreter
    command, drops every interpreter handle and collects again.  A
    root that survives that is refused with a named ``RuntimeError``
    naming the surviving holders - never a silent leak.
    """
    release_master_analysis_workers()
    root = box[0]
    box[0] = None
    if root is None:
        return
    app = root.tk
    try:
        root.update_idletasks()
    except TclError:
        pass
    try:
        root.destroy()
    except TclError:
        pass
    # RT-7: no interpreter command may outlive the root - the
    # variable-registered ones (search-field traces) are invisible
    # to destroy's own bookkeeping; release them before any handle
    # drops or collections (the local 'app' must not cross the
    # final collection, so it is cleared right after this call).
    _release_variable_traces(app)
    app = None
    for holder, name in clear:
        if hasattr(holder, name):
            setattr(holder, name, None)
    watch = weakref.ref(root)
    root = None
    gc.collect()
    if watch() is None:
        return
    if _drop_interpreter_and_collect(watch):
        return
    raise RuntimeError(
        "tk-teardown-refusal: tk-interpreter-release-failed - the "
        "destroyed root is still referenced after dropping every "
        "interpreter handle (holders: %s)"
        % _describe_holders(watch))
