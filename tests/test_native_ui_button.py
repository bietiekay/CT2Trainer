"""Regression: WP-58 chrome buttons must not pass duplicated widget kwargs.

0.16 shipped `TrainerWindow._button` with `font=`, `height=` and `pady=`
hard-coded as literal tk.Button kwargs on top of the `**style` spread.
`_chip` passes `width=`, `height=` and `font=` via kwargs, so every trainer
crashed at startup with
`TypeError: tkinter.Button() got multiple values for keyword argument 'height'`
(field report, Great Circle trainer from the 0.16 build, 2026-10-20).

The defaults now live inside the style dict so caller kwargs override them
instead of colliding.  A second WP-58 regression is covered here as well:
the pagination buttons passed the tuple `padx=(0, 4)` as a widget option,
which is a TclError ('bad screen distance') - the padding now lives in
`.pack()`.  The test builds the real widgets with every call-site
signature used in ui.py (tkinter is part of the shipped runtime; the
mock-based ui tests do not cover widget construction).
"""
from __future__ import annotations

import unittest

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - environment without Tcl/Tk
    tk = None

from ct2trainer.native.ui import TrainerWindow


@unittest.skipUnless(tk is not None, 'tkinter required for real widget construction')
class UiButtonKwargTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()

    def tearDown(self):
        self.root.destroy()

    def test_chip_signature_does_not_collide_with_button_defaults(self):
        # The exact call _chip issues (ui.py): width=9, height=2,
        # font=("Segoe UI", 11).  In 0.16 this raised the duplicate-kwarg
        # TypeError during _build_filters at trainer startup.
        window = TrainerWindow.__new__(TrainerWindow)
        window.set_view = lambda name: None
        button = window._chip(self.root, 'Switches')
        self.assertEqual(int(button.cget('height')), 2)
        self.assertIn('11', str(button.cget('font')))

    def test_defaults_apply_when_not_overridden(self):
        button = TrainerWindow._button(self.root, 'Close', lambda: None)
        self.assertEqual(int(button.cget('height')), 2)
        self.assertEqual(int(button.cget('pady')), 4)
        self.assertIn('12', str(button.cget('font')))

    def test_all_ui_call_site_signatures_build(self):
        # One case per _button call site in ui.py (header Close, header
        # status, filter chips, pagination): none may collide with the
        # merged defaults.
        TrainerWindow._button(self.root, 'Close', lambda: None,
                              bg='#000000', activebackground='#111111')
        TrainerWindow._button(self.root, 'Status / help', lambda: None,
                              width=12)
        TrainerWindow._button(self.root, 'Switches', lambda: None,
                              width=9, height=2, font=('Segoe UI', 11))
        TrainerWindow._button(self.root, 'Next', lambda: None, width=5)
        # The pagination padding lives in .pack(), not in the widget options:
        # a tuple padx as tk.Button option is a TclError ('bad screen
        # distance'), the second WP-58 regression caught by this test.
        TrainerWindow._button(self.root, 'Previous', lambda: None,
                              width=5).pack(side='right', padx=(0, 4))
        TrainerWindow._button(self.root, 'Top', lambda: None,
                              width=3).pack(side='right', padx=(0, 4))


if __name__ == '__main__':
    unittest.main()
