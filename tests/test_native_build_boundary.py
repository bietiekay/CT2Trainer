"""Verification prose refresh cannot misrepresent frozen implementation bytes."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile


SPEC=importlib.util.spec_from_file_location('owned_native_build',Path(__file__).resolve().parents[1]/'tools/native_build.py')
BUILD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class SourceRefreshBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.source=self.root/'src/ct2trainer/native/engine.py'
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'owned frozen implementation\n')
        self.document=self.root/'documentation/native-verification.md'
        self.document.parent.mkdir()
        self.document.write_bytes(b'old verification\n')
        self.output=self.root/'output'
        self.output.mkdir()
        self.archive=self.output/f'CT2Trainer-{BUILD.VERSION}-source.zip'
        with zipfile.ZipFile(self.archive,'w') as archive:
            archive.write(self.source,self.source.relative_to(self.root).as_posix())
            archive.write(self.document,self.document.relative_to(self.root).as_posix())
        self.report={'source_inputs':[{'path':self.source.relative_to(self.root).as_posix(),
                                      'sha256':BUILD.digest(self.source)}],
                     'outputs':[{'file':self.archive.name,'sha256':BUILD.digest(self.archive),
                                 'bytes':self.archive.stat().st_size}]}
        (self.output/'build.json').write_text(json.dumps(self.report),encoding='utf-8')
        self.addCleanup(patch.stopall)
        patch.object(BUILD,'ROOT',self.root).start()
        patch.object(BUILD,'source_files',return_value=[self.source]).start()

    def test_changed_implementation_refuses_without_overwriting_archive_or_report(self):
        original=self.archive.read_bytes()
        self.source.write_bytes(b'changed implementation\n')
        with self.assertRaisesRegex(ValueError,'fresh build'):
            BUILD.refresh_source(self.output)
        self.assertEqual(self.archive.read_bytes(),original)
        self.assertEqual(json.loads((self.output/'build.json').read_text()),self.report)
        self.assertFalse((self.output/'native-source-refresh.tmp').exists())

    def test_new_implementation_file_refuses_without_exporting_a_partial_snapshot(self):
        new=self.source.with_name('new_profile.py')
        new.write_bytes(b'new profile\n')
        original=self.archive.read_bytes()
        with patch.object(BUILD,'source_files',return_value=[self.source,new]):
            with self.assertRaisesRegex(ValueError,'fresh build'):
                BUILD.refresh_source(self.output)
        self.assertEqual(self.archive.read_bytes(),original)

    def test_verification_prose_updates_preserve_frozen_implementation_and_input_hashes(self):
        self.document.write_bytes(b'observed frozen verification\n')
        with patch('builtins.print'):
            BUILD.refresh_source(self.output)
        with zipfile.ZipFile(self.archive) as archive:
            self.assertEqual(archive.read('src/ct2trainer/native/engine.py'),self.source.read_bytes())
            self.assertEqual(archive.read('documentation/native-verification.md'),self.document.read_bytes())
        report=json.loads((self.output/'build.json').read_text())
        self.assertEqual(report['source_inputs'],self.report['source_inputs'])
        self.assertEqual(report['outputs'][0]['sha256'],BUILD.digest(self.archive))
        self.assertTrue(report['source_export_docs_refreshed_after_verification'])
