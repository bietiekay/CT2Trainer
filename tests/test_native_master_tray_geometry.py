"""Master Trainer 0.43: minimize-to-tray (MT-32) + window geometry
persistence (MT-33).

Covers the pure decision layers (``tray_model``: tray_message display
texts, TrayNotifier dedup, minimize_decision; ``window_geometry``:
capture / validate / restore with the documented clamp and the named
GeometryRefusal) and the Tk wiring on top: the persisted "Tray:"
status-bar toggle (on/off + persistence, the named refusals land in
the status line with the flag unchanged), the minimize-to-tray
intercept (an <Unmap> on the root withdraws the window only while the
feature is on and the window is visible; child-widget unmaps are
ignored), the tray-icon click restore, the attach / detach / attention
balloons (deduped, posted only while the feature is on and the icon
exists, a post failure never breaks the UI), the TrainerWindow
attach_observer contract (fired once per attach/detach transition in
the poll tick; the standalone default stays None), and the debounced
window-geometry save (one persist per quiet period, child-widget
Configure events ignored, withdrawn / closed windows keep the
previous value, the final save on close).

``TrayIcon`` / ``tray_available`` are patched for the wiring tests;
one win32-only smoke test exercises the real Shell_NotifyIconW seam
against the shipped Master_Trainer.ico (skipped with a named reason on
sessions where the OS refuses the window-class registration).
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

from ct2trainer.native.master_trainer.master_ui import MasterWindow
from ct2trainer.native.master_trainer import master_ui
from ct2trainer.native.master_trainer.master_state import (
    MASTER_STATE_SCHEMA,
    MasterState,
    MasterStateRefusal,
    load_master_state,
    save_master_state,
)
from ct2trainer.native.master_trainer.tray import TrayRefusal
from ct2trainer.native.master_trainer.tray_model import (
    TRAY_EVENT_ATTACHED,
    TRAY_EVENT_ATTENTION,
    TRAY_EVENT_DETACHED,
    TrayNotifier,
    minimize_decision,
    tray_message,
)
from ct2trainer.native.master_trainer.window_geometry import (
    GEOMETRY_BOUNDS,
    VISIBLE_MARGIN,
    GeometryRefusal,
    capture_geometry,
    default_geometry_spec,
    geometry_spec,
    restore_geometry,
    validate_geometry,
)
from native_tk_teardown import force_root_release
from test_native_master_ui import CT_GAMEA, _make_app

# Sentinel: the instance attribute did not exist before the override.
_MISSING = object()


class _StubRoot:
    """The minimal winfo surface capture_geometry reads."""

    def __init__(self, x=10, y=20, w=300, h=400, error=None):
        self._x, self._y, self._w, self._h = x, y, w, h
        self._error = error

    def _value(self, name, value):
        if self._error is not None:
            raise self._error
        return value

    def winfo_x(self):
        return self._value("x", self._x)

    def winfo_y(self):
        return self._value("y", self._y)

    def winfo_width(self):
        return self._value("width", self._w)

    def winfo_height(self):
        return self._value("height", self._h)


class TrayMessageTests(unittest.TestCase):
    """The pure balloon text builder (no OS seam involved)."""

    def test_attached_messages(self):
        self.assertEqual(
            tray_message(TRAY_EVENT_ATTACHED, table="a.ct",
                         process="GameA.exe"),
            ("Trainer attached", "a.ct is attached to GameA.exe."))
        self.assertEqual(
            tray_message(TRAY_EVENT_ATTACHED, table="a.ct"),
            ("Trainer attached", "a.ct is attached."))
        self.assertEqual(
            tray_message(TRAY_EVENT_ATTACHED, process="GameA.exe"),
            ("Trainer attached", "Attached to GameA.exe."))
        self.assertEqual(
            tray_message(TRAY_EVENT_ATTACHED),
            ("Trainer attached", "A trainer session is attached."))

    def test_detached_messages(self):
        self.assertEqual(
            tray_message(TRAY_EVENT_DETACHED, table="a.ct",
                         process="GameA.exe"),
            ("Target detached",
             "GameA.exe left; a.ct is no longer attached."))
        self.assertEqual(
            tray_message(TRAY_EVENT_DETACHED, table="a.ct"),
            ("Target detached", "a.ct is no longer attached."))
        self.assertEqual(
            tray_message(TRAY_EVENT_DETACHED),
            ("Target detached",
             "The target process is no longer attached."))

    def test_attention_carries_the_detail(self):
        title, body = tray_message(TRAY_EVENT_ATTENTION,
                                   detail="  named refusal here  ")
        self.assertEqual(title, "Trainer needs attention")
        self.assertEqual(body, "named refusal here")

    def test_unknown_event_raises(self):
        with self.assertRaises(ValueError):
            tray_message("bogus")

    def test_fields_are_trimmed_to_the_win32_limits(self):
        long_detail = "x" * 500
        title, body = tray_message(TRAY_EVENT_ATTENTION, detail=long_detail)
        self.assertLessEqual(len(body), 254)  # szInfo margin
        self.assertEqual(body, "x" * 254)
        long_table = "t" * 200
        _, body = tray_message(TRAY_EVENT_ATTACHED, table=long_table,
                               process="GameA.exe")
        self.assertLessEqual(len(body), 254)


class TrayNotifierTests(unittest.TestCase):
    """One balloon per distinct (event, body) pair."""

    def test_first_event_posts_and_repeat_is_deduped(self):
        notifier = TrayNotifier()
        first = notifier.observe(TRAY_EVENT_ATTACHED, table="a.ct",
                                 process="GameA.exe")
        self.assertIsNotNone(first)
        self.assertIsNone(notifier.observe(TRAY_EVENT_ATTACHED,
                                           table="a.ct",
                                           process="GameA.exe"))

    def test_changed_detail_posts_again(self):
        notifier = TrayNotifier()
        self.assertIsNotNone(notifier.observe(TRAY_EVENT_ATTENTION,
                                              detail="first"))
        self.assertIsNone(notifier.observe(TRAY_EVENT_ATTENTION,
                                           detail="first"))
        self.assertIsNotNone(notifier.observe(TRAY_EVENT_ATTENTION,
                                              detail="second"))

    def test_event_flip_posts_again(self):
        notifier = TrayNotifier()
        self.assertIsNotNone(notifier.observe(TRAY_EVENT_ATTACHED))
        self.assertIsNotNone(notifier.observe(TRAY_EVENT_DETACHED))
        self.assertIsNotNone(notifier.observe(TRAY_EVENT_ATTACHED))

    def test_context_change_posts_again(self):
        notifier = TrayNotifier()
        self.assertIsNotNone(notifier.observe(TRAY_EVENT_ATTACHED,
                                              table="a.ct"))
        self.assertIsNotNone(notifier.observe(TRAY_EVENT_ATTACHED,
                                              table="b.ct"))


class MinimizeDecisionTests(unittest.TestCase):
    """Divert to the tray only while the feature is on AND visible."""

    def test_decision_matrix(self):
        self.assertTrue(minimize_decision(True, False))
        self.assertFalse(minimize_decision(True, True))
        self.assertFalse(minimize_decision(False, False))
        self.assertFalse(minimize_decision(False, True))


class WindowGeometryPureTests(unittest.TestCase):
    """The pure capture / validate / restore layer (no Tk needed)."""

    def test_default_geometry_spec(self):
        self.assertEqual(default_geometry_spec(), "1160x600")

    def test_capture_geometry_ok(self):
        self.assertEqual(capture_geometry(_StubRoot(10, 20, 300, 400)),
                         {"x": 10, "y": 20, "w": 300, "h": 400})

    def test_capture_geometry_refused_on_torn_down_root(self):
        root = _StubRoot(error=Exception("widget gone"))
        self.assertIsNone(capture_geometry(root))

    def test_capture_geometry_refused_on_degenerate_size(self):
        self.assertIsNone(capture_geometry(_StubRoot(0, 0, 0, 0)))
        self.assertIsNone(capture_geometry(_StubRoot(0, 0, -5, 100)))

    def test_geometry_spec(self):
        self.assertEqual(geometry_spec({"x": 1, "y": 2, "w": 3, "h": 4}),
                         "3x4+1+2")

    def test_validate_none_is_valid(self):
        validate_geometry(None)  # nothing stored: the documented default

    def test_validate_bad_shapes_refused(self):
        bad_values = (
            "null", 32, [1, 2, 3, 4],
            {"x": 0, "y": 0, "w": 10},
            {"x": 0, "y": 0, "w": 10, "h": 10, "z": 1},
            {"x": 0.0, "y": 0, "w": 10, "h": 10},
            {"x": "0", "y": 0, "w": 10, "h": 10},
            {"x": 0, "y": 0, "w": -1, "h": 10},
            {"x": 20000, "y": 0, "w": 10, "h": 10},
            {"x": 0, "y": -20000, "w": 10, "h": 10},
        )
        for bad in bad_values:
            with self.assertRaises(GeometryRefusal):
                validate_geometry(bad)

    def test_geometry_refusal_reason(self):
        with self.assertRaises(GeometryRefusal) as ctx:
            validate_geometry({"x": 0, "y": 0, "w": 10})
        self.assertEqual(ctx.exception.reason, "window-geometry-invalid")
        self.assertIsInstance(ctx.exception.detail, str)

    def test_restore_none_gives_the_default(self):
        self.assertEqual(restore_geometry(None, 1920, 1080), "1160x600")

    def test_restore_in_bounds_kept(self):
        self.assertEqual(
            restore_geometry({"x": 50, "y": 40, "w": 1400, "h": 700},
                             1920, 1080),
            "1400x700+50+40")

    def test_restore_clamps_the_size_to_the_screen(self):
        self.assertEqual(
            restore_geometry({"x": 0, "y": 0, "w": 5000, "h": 5000},
                             1920, 1080),
            "1920x1080+0+0")

    def test_restore_never_below_the_documented_minimum(self):
        self.assertEqual(
            restore_geometry({"x": 0, "y": 0, "w": 50, "h": 50},
                             1920, 1080),
            "320x240+0+0")

    def test_restore_pulls_a_far_offscreen_window_back(self):
        # x far to the right: at least VISIBLE_MARGIN stays visible.
        self.assertEqual(
            restore_geometry({"x": 9000, "y": 0, "w": 800, "h": 600},
                             1920, 1080),
            "800x600+%d+0" % (1920 - VISIBLE_MARGIN))
        # y far above the screen: the window bottom stays visible.
        self.assertEqual(
            restore_geometry({"x": 0, "y": -9000, "w": 800, "h": 600},
                             1920, 1080),
            "800x600+0+%d" % -(600 - VISIBLE_MARGIN))

    def test_restore_refuses_out_of_bounds_documents(self):
        with self.assertRaises(GeometryRefusal):
            restore_geometry({"x": GEOMETRY_BOUNDS + 1, "y": 0,
                              "w": 100, "h": 100}, 1920, 1080)


class MasterTrayWiringBase(unittest.TestCase):
    """The real-Tk wiring with the OS seam (TrayIcon) patched out.

    The seam patch lives for the whole test (entered in setUp), so the
    toggle handlers always see the mock - a context that ended before
    the handler ran would leak the real (session-restricted) seam.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(self._rmtree)
        self.folder = self.tmp / "tables"
        self.folder.mkdir()
        self.state_home = self.tmp / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = _make_app(self.folder, self.state_home)
        self.window = MasterWindow(self.root, self.app)
        self.icon_cls = MagicMock()
        self.available_mock = patch.object(
            master_ui, "tray_available", return_value=True).start()
        self.icon_patch = patch.object(master_ui, "TrayIcon",
                                       self.icon_cls).start()
        self.addCleanup(self.icon_patch.stop)
        self.addCleanup(self.available_mock.stop)
        self.addCleanup(self._safe_close)

    def _rmtree(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _safe_close(self):
        try:
            alive = self.root.winfo_exists()
        except Exception:
            alive = False
        if alive:
            try:
                self.window.close()
            except Exception:
                try:
                    self.root.destroy()
                except Exception:
                    pass
        force_root_release([self.root], ((self, "root"),))

    def _tray_state_file(self):
        return load_master_state(self.app.state_path())

    @contextmanager
    def _override_root(self, **attrs):
        """Override the root's dynamic winfo_* / window methods for one
        test step.

        tkinter generates the winfo_* commands on demand, so
        unittest.mock.patch.object cannot see them; a plain instance
        attribute shadows the generated one and is restored after the
        step (the original instance-dict entry, when present, wins).
        """
        saved = {}
        for name, value in attrs.items():
            saved[name] = self.root.__dict__.get(name, _MISSING)
            setattr(self.root, name, value)
        try:
            yield
        finally:
            for name, original in saved.items():
                if original is _MISSING:
                    self.root.__dict__.pop(name, None)
                else:
                    setattr(self.root, name, original)

    def _set_platform_unavailable(self):
        self.available_mock.return_value = False

    def _set_icon_error(self, exc):
        self.icon_cls.side_effect = exc


@unittest.skipUnless(tk is not None,
                     "tkinter required for real widget construction")
class TrayToggleTests(MasterTrayWiringBase):
    """The persisted status-bar toggle (default off, opt-in)."""

    def test_feature_defaults_off(self):
        self.assertFalse(self.app.tray_minimize)
        self.assertIsNone(self.window._tray)
        self.assertEqual(self.window._tray_btn.cget("text"), "Tray: off")

    def test_toggle_on_persists_and_arms_the_icon(self):
        self.window._toggle_tray()
        self.assertTrue(self.app.tray_minimize)
        self.icon_cls.assert_called_once()
        self.assertIs(self.window._tray, self.icon_cls.return_value)
        self.assertEqual(self.window._tray_btn.cget("text"), "Tray: on")
        self.assertTrue(self._tray_state_file().tray_minimize)

    def test_toggle_off_removes_the_icon_and_persists(self):
        self.window._toggle_tray()
        self.window._toggle_tray()
        self.assertFalse(self.app.tray_minimize)
        self.assertIsNone(self.window._tray)
        self.icon_cls.return_value.remove.assert_called_once()
        self.assertEqual(self.window._tray_btn.cget("text"), "Tray: off")
        self.assertFalse(self._tray_state_file().tray_minimize)

    def test_toggle_refused_on_non_windows_platforms(self):
        self._set_platform_unavailable()
        self.window._toggle_tray()
        self.assertFalse(self.app.tray_minimize)  # flag untouched
        self.assertIsNone(self.window._tray)
        self.icon_cls.assert_not_called()
        self.assertIn("Tray unavailable", self.window._status_var.get())
        # The refused change is never persisted: the state home still
        # carries no document at all (the flag never left False).
        self.assertIsNone(self._tray_state_file())

    def test_toggle_refused_on_missing_icon(self):
        icon = self.folder / "missing.ico"
        with patch.object(master_ui, "window_icon_path",
                          return_value=icon):
            self.window._toggle_tray()
        self.assertFalse(self.app.tray_minimize)
        self.assertIsNone(self.window._tray)
        self.assertIn("Tray setup failed", self.window._status_var.get())

    def test_toggle_refused_on_win32_setup_failure(self):
        self._set_icon_error(TrayRefusal(
            "tray-setup-failed",
            "Shell_NotifyIconW(NIM_ADD) failed (Win32 error 42)"))
        self.window._toggle_tray()
        self.assertFalse(self.app.tray_minimize)
        self.assertIsNone(self.window._tray)
        self.assertIn("Tray setup failed", self.window._status_var.get())
        self.assertIn("Win32 error 42", self.window._status_var.get())


@unittest.skipUnless(tk is not None,
                     "tkinter required for real widget construction")
class MinimizeInterceptTests(MasterTrayWiringBase):
    """A pending minimize diverts into the tray while the feature is on."""

    def test_minimize_diverts_to_the_tray_when_on(self):
        self.window._toggle_tray()
        withdraw = MagicMock()
        with self._override_root(winfo_withdrawn=lambda: False,
                                 withdraw=withdraw):
            self.window._on_root_unmap(MagicMock(widget=self.root))
        withdraw.assert_called_once()

    def test_minimize_untouched_when_the_feature_is_off(self):
        withdraw = MagicMock()
        with self._override_root(winfo_withdrawn=lambda: False,
                                 withdraw=withdraw):
            self.window._on_root_unmap(MagicMock(widget=self.root))
        withdraw.assert_not_called()

    def test_an_already_hidden_window_stays_hidden(self):
        self.window._toggle_tray()
        withdraw = MagicMock()
        with self._override_root(winfo_withdrawn=lambda: True,
                                 withdraw=withdraw):
            self.window._on_root_unmap(MagicMock(widget=self.root))
        withdraw.assert_not_called()

    def test_child_widget_unmaps_are_ignored(self):
        self.window._toggle_tray()
        child = tk.Frame(self.root)
        self.addCleanup(child.destroy)
        withdraw = MagicMock()
        with self._override_root(winfo_withdrawn=lambda: False,
                                 withdraw=withdraw):
            self.window._on_root_unmap(MagicMock(widget=child))
        withdraw.assert_not_called()

    def test_tray_restore_brings_the_window_back(self):
        with patch.object(self.root, "deiconify") as deiconify, \
                patch.object(self.root, "lift") as lift, \
                patch.object(self.root, "focus_force") as focus:
            self.window._tray_restore()
        deiconify.assert_called_once()
        lift.assert_called_once()
        focus.assert_called_once()


@unittest.skipUnless(tk is not None,
                     "tkinter required for real widget construction")
class TrayBalloonTests(MasterTrayWiringBase):
    """Attach / detach / attention balloons, deduped and fail-safe."""

    def _tray_on(self):
        self.window._toggle_tray()
        self.window._tray_table = "a.ct"
        self.window._tray_process = "GameA.exe"
        return self.window._tray

    def test_attached_balloon_is_posted(self):
        tray = self._tray_on()
        self.window._on_attach_observer(TRAY_EVENT_ATTACHED)
        tray.show_balloon.assert_called_once_with(
            "Trainer attached", "a.ct is attached to GameA.exe.")

    def test_repeated_event_is_deduped(self):
        tray = self._tray_on()
        self.window._on_attach_observer(TRAY_EVENT_ATTACHED)
        self.window._on_attach_observer(TRAY_EVENT_ATTACHED)
        self.assertEqual(tray.show_balloon.call_count, 1)

    def test_detached_after_attached_posts_once_each(self):
        tray = self._tray_on()
        self.window._on_attach_observer(TRAY_EVENT_ATTACHED)
        self.window._on_attach_observer(TRAY_EVENT_DETACHED)
        self.assertEqual(tray.show_balloon.call_count, 2)

    def test_attention_from_a_failed_trainer_start(self):
        tray = self._tray_on()
        with patch.object(self.app.orchestrator, "fail_load") as fail_load:
            self.window._fail_trainer_start("state lock: named reason")
        fail_load.assert_called_once_with("state lock: named reason")
        tray.show_balloon.assert_called_once_with(
            "Trainer needs attention", "state lock: named reason")
        self.assertIn("Trainer start failed", self.window._status_var.get())

    def test_attention_with_changed_detail_posts_again(self):
        tray = self._tray_on()
        with patch.object(self.app.orchestrator, "fail_load"):
            self.window._fail_trainer_start("first")
            self.window._fail_trainer_start("first")
            self.window._fail_trainer_start("second")
        self.assertEqual(tray.show_balloon.call_count, 2)

    def test_no_balloon_while_the_feature_is_off(self):
        tray = MagicMock()
        self.window._tray = tray
        self.window._tray_table = "a.ct"
        self.window._tray_process = "GameA.exe"
        self.window._on_attach_observer(TRAY_EVENT_ATTACHED)
        tray.show_balloon.assert_not_called()

    def test_no_balloon_without_a_live_icon(self):
        self.app.tray_minimize = True
        self.window._tray = None
        self.window._on_attach_observer(TRAY_EVENT_ATTACHED)  # no raise

    def test_a_post_failure_never_breaks_the_ui(self):
        tray = self._tray_on()
        tray.show_balloon.side_effect = RuntimeError("seam gone")
        self.window._on_attach_observer(TRAY_EVENT_ATTACHED)  # no raise


@unittest.skipUnless(tk is not None,
                     "tkinter required for real widget construction")
class TrainerObserverTests(unittest.TestCase):
    """The TrainerWindow attach/detach transition observer (ui.py)."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        force_root_release([self.root], ((self, "root"),))

    def _engine(self):
        e = MagicMock()
        e.entries = {}
        e.status = "idle"
        e.plan = {"title": "T", "process_name": "GameA.exe",
                  "table_sha256": "ab" * 32, "entries": []}
        e.applied = set()
        e.desired = set()
        e.frozen = set()
        e.entry_errors = {}
        e.enable_failures = set()
        e.rearm = {}
        e.memory = None
        e.hotkey_warnings = []
        e.closed = False
        e.connected = False
        e.blocked = False
        e.poll = lambda: "idle"
        e.pop_hotkey_ui_toggles = lambda: []
        return e

    def test_observer_defaults_none(self):
        from ct2trainer.native.ui import TrainerWindow
        import inspect
        sig = inspect.signature(TrainerWindow.__init__)
        self.assertIn("attach_observer", sig.parameters)
        self.assertIsNone(sig.parameters["attach_observer"].default)

    def _window(self, observer, engine):
        from ct2trainer.native.ui import TrainerWindow
        window = TrainerWindow(self.root, engine, attach_observer=observer)
        # The poll tick under test only needs the transition logic, not
        # the row grid: keep the render side effects out of the loop.
        window.render = lambda: None
        window._refresh_value_texts = lambda: None
        return window

    def test_poll_fires_attached_on_the_transition(self):
        events = []
        engine = self._engine()
        memory = object()
        engine.poll = lambda: (setattr(engine, "memory", memory),
                               "attached")[1]
        window = self._window(events.append, engine)
        with patch("ct2trainer.native.ui.play_sound"):
            window.poll()
        self.assertEqual(events, ["attached"])

    def test_poll_fires_detached_when_the_target_exits(self):
        events = []
        engine = self._engine()
        engine.memory = object()
        engine.poll = lambda: (setattr(engine, "memory", None),
                               "target gone")[1]
        window = self._window(events.append, engine)
        with patch("ct2trainer.native.ui.play_sound"):
            window.poll()
        self.assertEqual(events, ["detached"])

    def test_poll_is_silent_in_the_steady_state(self):
        events = []
        engine = self._engine()
        engine.memory = object()
        window = self._window(events.append, engine)
        with patch("ct2trainer.native.ui.play_sound"):
            window.poll()
            window.poll()
        self.assertEqual(events, [])

    def test_observer_failure_never_breaks_the_poll_tick(self):
        def bad_observer(_event):
            raise RuntimeError("observer crashed")
        engine = self._engine()
        memory = object()
        engine.poll = lambda: (setattr(engine, "memory", memory),
                               "attached")[1]
        window = self._window(bad_observer, engine)
        with patch("ct2trainer.native.ui.play_sound"):
            window.poll()  # must not raise
        self.assertEqual(engine.status, "idle")

    def test_standalone_trainer_has_no_observer(self):
        from ct2trainer.native.ui import TrainerWindow
        engine = self._engine()
        window = TrainerWindow(self.root, engine)
        window.render = lambda: None
        window._refresh_value_texts = lambda: None
        memory = object()
        engine.poll = lambda: (setattr(engine, "memory", memory),
                               "attached")[1]
        with patch("ct2trainer.native.ui.play_sound"):
            window.poll()
        self.assertIsNone(window.attach_observer)


@unittest.skipUnless(tk is not None,
                     "tkinter required for real widget construction")
class WindowGeometryRestoreTests(unittest.TestCase):
    """The restore pass at start (fresh root + app per test)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(self._rmtree)
        self.folder = self.tmp / "tables"
        self.folder.mkdir()
        self.state_home = self.tmp / "state"
        self.state_home.mkdir()
        (self.folder / "a.ct").write_text(CT_GAMEA, encoding="utf-8")
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self._safe_close)

    def _rmtree(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _safe_close(self):
        try:
            alive = self.root.winfo_exists()
        except Exception:
            alive = False
        if alive:
            try:
                self.root.destroy()
            except Exception:
                pass
        force_root_release([self.root], ((self, "root"),))

    def _window_with_state(self):
        app = _make_app(self.folder, self.state_home)
        window = MasterWindow(self.root, app)
        self.addCleanup(window._deactivate_tray)
        return app, window

    def test_window_uses_the_documented_default_size(self):
        _, window = self._window_with_state()
        self.assertEqual(window._window_size_spec, "1160x600")

    def test_restore_a_stored_geometry_at_start(self):
        save_master_state(MasterState(
            MASTER_STATE_SCHEMA, str(self.folder),
            window_geometry={"x": 25, "y": 15, "w": 1250, "h": 650},
            table_folders=(str(self.folder),)),
            self.state_home / "master-settings.json")
        _, window = self._window_with_state()
        self.assertEqual(window._window_size_spec, "1250x650+25+15")

    def test_restore_refusal_falls_back_to_the_default_size(self):
        # The state layer normally refuses out-of-bounds geometry first;
        # the window's own catch is defense in depth: a refused restore
        # keeps the default size and names the reason in the status line.
        with patch.object(master_ui, "restore_geometry",
                          side_effect=GeometryRefusal(
                              "window-geometry-invalid", "boom")):
            _, window = self._window_with_state()
        self.assertEqual(window._window_size_spec, "1160x600")
        self.assertIn("Stored window geometry refused",
                      window._status_var.get())
        self.assertIn("boom", window._status_var.get())

    def test_out_of_bounds_geometry_is_refused_at_the_state_layer(self):
        with self.assertRaises(MasterStateRefusal):
            save_master_state(MasterState(
                MASTER_STATE_SCHEMA, str(self.folder),
                window_geometry={"x": 0, "y": 0, "w": 99999, "h": 100},
                table_folders=(str(self.folder),)),
                self.state_home / "master-settings.json")


@unittest.skipUnless(tk is not None,
                     "tkinter required for real widget construction")
class WindowGeometryWiringTests(MasterTrayWiringBase):
    """The debounced geometry save (the waiting-view root)."""

    def test_configure_schedules_the_debounced_save(self):
        self.window._on_root_configure(MagicMock(widget=self.root))
        self.assertIsNotNone(self.window._geometry_save_job)

    def test_child_configure_is_ignored(self):
        child = tk.Frame(self.root)
        self.addCleanup(child.destroy)
        self.window._on_root_configure(MagicMock(widget=child))
        self.assertIsNone(self.window._geometry_save_job)

    def test_save_geometry_persists_and_syncs_the_spec(self):
        self.window._on_root_configure(MagicMock(widget=self.root))
        with self._override_root(winfo_x=lambda: 12,
                                 winfo_y=lambda: 8,
                                 winfo_width=lambda: 1310,
                                 winfo_height=lambda: 720,
                                 winfo_withdrawn=lambda: False):
            self.window._save_geometry()
        self.assertIsNone(self.window._geometry_save_job)
        self.assertEqual(self.window.app.window_geometry,
                         {"x": 12, "y": 8, "w": 1310, "h": 720})
        self.assertEqual(self.window._window_size_spec, "1310x720+12+8")
        self.assertEqual(self._tray_state_file().window_geometry,
                         {"x": 12, "y": 8, "w": 1310, "h": 720})

    def test_save_geometry_keeps_the_previous_value_when_withdrawn(self):
        self.window._on_root_configure(MagicMock(widget=self.root))
        self.window._save_geometry()  # the harness root is withdrawn
        self.assertIsNone(self.window.app.window_geometry)

    def test_save_geometry_is_suppressed_after_close(self):
        self.app.closed = True
        self.window._save_geometry()
        self.assertIsNone(self.window.app.window_geometry)

    def test_save_final_geometry_persists_the_final_window(self):
        with self._override_root(winfo_x=lambda: 33,
                                 winfo_y=lambda: 44,
                                 winfo_width=lambda: 1400,
                                 winfo_height=lambda: 800,
                                 winfo_withdrawn=lambda: False):
            self.window._save_final_geometry()
        self.assertEqual(self._tray_state_file().window_geometry,
                         {"x": 33, "y": 44, "w": 1400, "h": 800})

    def test_close_saves_the_geometry_first_and_removes_the_tray(self):
        self.window._toggle_tray()
        calls = []
        with patch.object(self.window, "_save_final_geometry",
                          side_effect=lambda: calls.append("geometry")), \
                patch.object(self.window, "_deactivate_tray",
                             side_effect=lambda: calls.append("tray")):
            self.window.close()
        self.assertEqual(calls, ["geometry", "tray"])
        self.assertTrue(self.app.closed)

    def test_close_removes_the_live_tray_icon(self):
        self.window._toggle_tray()
        self.window.close()
        self.icon_cls.return_value.remove.assert_called_once()
        self.assertIsNone(self.window._tray)


@unittest.skipUnless(sys.platform == "win32" and tk is not None,
                     "the real tray smoke test needs Windows + tkinter")
class TrayIconWindowsSmokeTests(unittest.TestCase):
    """The real Shell_NotifyIconW seam against the shipped icon.

    Skipped with a named reason when the OS refuses the window-class
    registration (some non-interactive / restricted sessions block
    RegisterClassExW; the feature stays off fail-closed there - the
    exact path the toggle wiring tests prove with the named refusal).
    """

    def test_real_icon_roundtrip_and_click_restore(self):
        import ctypes
        from ct2trainer.native.window_icon import window_icon_path
        from ct2trainer.native.master_trainer.tray import TrayIcon

        icon = window_icon_path("master")
        self.assertTrue(icon.is_file(), str(icon))
        root = tk.Tk()
        root.withdraw()
        self.addCleanup(root.destroy)
        clicks = []
        try:
            tray = TrayIcon(str(icon), lambda: clicks.append(1))
        except TrayRefusal as exc:
            self.skipTest(
                "the session refuses the tray setup: %s (%s)"
                % (exc.code, exc.detail))
        except Exception as exc:  # a stripped user32 / restricted session
            self.skipTest(
                "the session cannot run the real tray seam: %r" % exc)
        self.addCleanup(tray.remove)
        self.assertTrue(tray.show_balloon("smoke", "balloon round-trip"))
        # Pump the hidden window's message queue with a real left-click
        # on the icon (WM_LBUTTONUP); the Tk update loop delivers it.
        user32 = ctypes.windll.user32
        user32.PostMessageW.argtypes = [ctypes.wintypes.HWND,
                                        ctypes.wintypes.UINT,
                                        ctypes.wintypes.WPARAM,
                                        ctypes.wintypes.LPARAM]
        user32.PostMessageW(tray._hwnd, 0x0202, 1, 0)  # WM_LBUTTONUP
        for _ in range(100):
            if clicks:
                break
            root.update()
        self.assertEqual(clicks, [1])
        tray.remove()
        tray.remove()  # idempotent
        self.assertIsNone(tray._hwnd)
        self.assertIsNone(tray._hicon)


if __name__ == "__main__":
    unittest.main()
