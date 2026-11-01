"""Master Trainer SteamOS / CheatDeck target route (MT-7): the documented
route surface.

Covers: the per-platform ``attach_gate`` decision, the fail-closed
``require_engine_attach`` refusal (named error carrying the documented
route text), ``route_text`` for the UI status line, ``detect_platform``
on the host, and the module's platform purity (clean import, no
Windows-specific API surface in the source). The owned Linux attach
backend stays explicitly out of scope (fail-closed refusal surface only).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from ct2trainer.native.master_trainer import steamdeck_route as dr
from ct2trainer.native.master_trainer.steamdeck_route import (
    AttachRoute,
    DeckAttachUnavailableError,
    STEAMDECK_ROUTE_TEXT,
    attach_gate,
    detect_platform,
    require_engine_attach,
    route_text,
)


class SteamdeckRouteTests(unittest.TestCase):
    # ------------------------------------------------------- attach_gate

    def test_windows_gate_available_native_engine_route(self):
        route = attach_gate("windows")
        self.assertIsInstance(route, AttachRoute)
        self.assertEqual(route.platform, "windows")
        self.assertTrue(route.attach_available)
        self.assertEqual(route.route_name, "native-windows-engine")
        self.assertTrue(route.detail)

    def test_linux_gate_unavailable_proton_wrapped_route(self):
        route = attach_gate("linux")
        self.assertEqual(route.platform, "linux")
        self.assertFalse(route.attach_available)
        self.assertEqual(route.route_name, "steamdeck-proton-wrapped")
        detail = route.detail.lower()
        self.assertIn("proton-wrapped standalone", detail)
        self.assertIn("cheatdeck", detail)
        self.assertIn("detection, table index and waiting ui only", detail)
        self.assertIn("fail-closed", detail)

    def test_other_gate_unavailable_same_route(self):
        route = attach_gate("other")
        self.assertEqual(route.platform, "other")
        self.assertFalse(route.attach_available)
        self.assertEqual(route.route_name, "steamdeck-proton-wrapped")
        self.assertEqual(route.detail, STEAMDECK_ROUTE_TEXT)

    def test_unknown_platform_folds_to_other_and_refuses(self):
        route = attach_gate("freebsd")
        self.assertEqual(route.platform, "other")
        self.assertFalse(route.attach_available)
        self.assertEqual(route.route_name, "steamdeck-proton-wrapped")

    def test_none_platform_uses_host(self):
        self.assertEqual(attach_gate().platform, detect_platform())

    # ------------------------------------------------- require_engine_attach

    def test_require_engine_attach_windows_returns_route(self):
        route = require_engine_attach("windows")
        self.assertIsInstance(route, AttachRoute)
        self.assertTrue(route.attach_available)
        self.assertEqual(route.route_name, "native-windows-engine")

    def test_require_engine_attach_linux_raises_named_error(self):
        for plat in ("linux", "other", "freebsd"):
            with self.subTest(plat=plat):
                with self.assertRaises(DeckAttachUnavailableError) as cm:
                    require_engine_attach(plat)
                self.assertEqual(str(cm.exception), STEAMDECK_ROUTE_TEXT)
                self.assertIsInstance(cm.exception.route, AttachRoute)
                self.assertFalse(cm.exception.route.attach_available)

    def test_require_engine_attach_error_is_value_error(self):
        self.assertTrue(issubclass(DeckAttachUnavailableError, ValueError))

    # ------------------------------------------------------------ route_text

    def test_route_text_windows_names_available_path(self):
        text = route_text("windows")
        self.assertIn("native Windows engine", text)
        self.assertNotIn("fail-closed", text.lower())

    def test_route_text_non_windows_carries_refusal(self):
        for plat in ("linux", "other"):
            with self.subTest(plat=plat):
                text = route_text(plat)
                self.assertEqual(text, STEAMDECK_ROUTE_TEXT)
                self.assertIn("Proton-wrapped standalone", text)

    # ------------------------------------------------------- host detection

    def test_detect_platform_on_this_host(self):
        if sys.platform == "win32":
            self.assertEqual(detect_platform(), "windows")
        elif sys.platform.startswith("linux"):
            self.assertEqual(detect_platform(), "linux")
        else:
            self.assertEqual(detect_platform(), "other")

    # ------------------------------------------------------ platform purity

    def test_module_source_has_no_windows_only_apis(self):
        source = Path(dr.__file__).read_text(encoding="utf-8")
        for forbidden in ("windll", "Win32", "winreg", "ctypes",
                          "Toolhelp32", "kernel32", "user32", "advapi32"):
            self.assertNotIn(forbidden, source, forbidden)

    def test_module_imports_cleanly(self):
        # The import at the top of this file already proved the module
        # loads; assert the pure stdlib surface is intact.
        import importlib
        module = importlib.import_module(
            "ct2trainer.native.master_trainer.steamdeck_route")
        self.assertTrue(callable(module.detect_platform))
        self.assertTrue(callable(module.attach_gate))
        self.assertTrue(callable(module.require_engine_attach))
        self.assertTrue(callable(module.route_text))
