"""Window titles and the shared repository link label for both UIs."""
from __future__ import annotations

import webbrowser
import tkinter as tk

from .. import REPO_URL, __version__


def converter_title() -> str:
    """Exact converter window title: product name, build version, role."""
    return "CT2Trainer " + __version__ + " — independent CT converter"


def trainer_title(plan_title: str) -> str:
    """Exact trainer window title: plan title, product name, build version."""
    return plan_title + " — CT2Trainer " + __version__


def repo_link(parent, **label_options):
    """Clickable GitHub repository label.

    The URL text and hand cursor are fixed by contract; caller-supplied
    label options are merged for styling only and never override them.
    Clicking the label opens REPO_URL in the default web browser.
    """
    options = {key: value for key, value in label_options.items()
               if key not in ("text", "cursor")}
    options["text"] = REPO_URL
    options["cursor"] = "hand2"
    label = tk.Label(parent, **options)
    label.bind("<Button-1>", lambda *_: webbrowser.open(REPO_URL))
    return label
