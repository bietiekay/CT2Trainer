"""Build version in window titles and the GitHub repository link in both UIs.

Window titles carry the build version (WP-17); both the converter and the
trainer show a clickable link to the repository. ``verify_version_sync``
fails the build when the runtime ``__version__`` constant drifts from the
root ``VERSION`` file, which remains the single version source.
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ct2trainer import REPO_URL, __version__
from ct2trainer.native import about_ui
from ct2trainer.native.about_ui import converter_title, repo_link, trainer_title

ROOT = Path(__file__).resolve().parents[1]

SPEC = importlib.util.spec_from_file_location(
    'wp17_version_native_build', ROOT / 'tools/native_build.py')
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class VersionConstantsTests(unittest.TestCase):
    def test_version_matches_root_version_file(self):
        expected = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
        self.assertEqual(__version__, expected)

    def test_repo_url_is_exact(self):
        self.assertEqual(REPO_URL, 'https://github.com/bietiekay/CT2Trainer')

    def test_converter_title_contract(self):
        self.assertEqual(
            converter_title(),
            'CT2Trainer ' + __version__ + ' — independent CT converter')

    def test_trainer_title_contract(self):
        self.assertEqual(
            trainer_title('Demo'), 'Demo — CT2Trainer ' + __version__)


class _RecordingLabel:
    """tk.Label stand-in recording constructor kwargs and bindings."""

    def __init__(self, parent, **kwargs):
        self.parent = parent
        self.kwargs = kwargs
        self.bindings = {}

    def bind(self, sequence, handler):
        self.bindings[sequence] = handler


class RepoLinkTests(unittest.TestCase):
    def test_repo_link_carries_url_and_hand_cursor(self):
        with patch('ct2trainer.native.about_ui.tk.Label', _RecordingLabel), \
                patch('ct2trainer.native.about_ui.webbrowser') as web:
            label = about_ui.repo_link('parent-frame')
        self.assertIs(label.parent, 'parent-frame')
        self.assertEqual(label.kwargs['text'], REPO_URL)
        self.assertEqual(label.kwargs['cursor'], 'hand2')

    def test_repo_link_click_opens_repository_once(self):
        with patch('ct2trainer.native.about_ui.tk.Label', _RecordingLabel), \
                patch('ct2trainer.native.about_ui.webbrowser') as web:
            label = about_ui.repo_link('parent-frame')
            label.bindings['<Button-1>'](None)
        web.open.assert_called_once_with(REPO_URL)

    def test_repo_link_merges_styling_without_overriding_contract_fields(self):
        with patch('ct2trainer.native.about_ui.tk.Label', _RecordingLabel), \
                patch('ct2trainer.native.about_ui.webbrowser'):
            label = about_ui.repo_link('parent-frame', bg='#181f2b', fg='#f2f5fa',
                                       text='forged', cursor='nope')
        self.assertEqual(label.kwargs['bg'], '#181f2b')
        self.assertEqual(label.kwargs['fg'], '#f2f5fa')
        self.assertEqual(label.kwargs['text'], REPO_URL)
        self.assertEqual(label.kwargs['cursor'], 'hand2')


class VerifyVersionSyncTests(unittest.TestCase):
    def _pair(self, version, init_source):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        version_file = root / 'VERSION'
        init_file = root / '__init__.py'
        version_file.write_text(version, encoding='utf-8')
        init_file.write_text(init_source, encoding='utf-8')
        return version_file, init_file

    def test_matching_pair_passes(self):
        version_file, init_file = self._pair('0.10\n',
                                             '"""pkg"""\n__version__ = "0.10"\n')
        self.assertEqual(BUILD.verify_version_sync(version_file, init_file), '0.10')

    def test_drifted_version_raises(self):
        version_file, init_file = self._pair('0.10\n', '__version__ = "0.9.9"\n')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            BUILD.verify_version_sync(version_file, init_file)

    def test_missing_constant_raises(self):
        version_file, init_file = self._pair('0.10\n', '"""pkg"""\n# no constant\n')
        with self.assertRaisesRegex(ValueError, 'missing'):
            BUILD.verify_version_sync(version_file, init_file)
