"""Independent big-integer oracle for the optional owned Windows C fixture.

Build with tests/windows/clock_fixture/Invoke-ClockFixture.ps1, then set
CT2TRAINER_CLOCK_FIXTURE to its NativeClockFixture.exe. No compilation, target
attachment, or arbitrary module loading occurs during ordinary unit discovery.
"""
import json
import os
from pathlib import Path
import subprocess
import unittest


@unittest.skipUnless(os.name == "nt" and os.environ.get("CT2TRAINER_CLOCK_FIXTURE"),
                     "owned Windows clock fixture not supplied")
class NativeClockFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        executable = Path(os.environ["CT2TRAINER_CLOCK_FIXTURE"])
        cls.result = subprocess.run([str(executable)], capture_output=True,
                                    text=True, timeout=20, check=True)
        cls.observed = json.loads(cls.result.stdout)

    def test_local_rate_epoch_lease_fault_and_concurrency_contract(self):
        self.assertEqual(self.result.stderr, "")
        self.assertEqual(self.observed["schema"], "ct2trainer-clock-fixture/v1")
        self.assertIn(self.observed["pointer_bits"], (32, 64))
        self.assertGreaterEqual(self.observed["checks"], 1100)

    def test_conversion_against_arbitrary_precision_reference(self):
        self.assertEqual(len(self.observed["vectors"]), 256)
        overflow_cases = 0
        for case in self.observed["vectors"]:
            with self.subTest(case=case):
                expected = int(case["ticks"]) * 1000 // int(case["frequency"])
                if expected > (1 << 64) - 1:
                    overflow_cases += 1
                    self.assertEqual(case["status"], 4)
                    self.assertEqual(int(case["milliseconds"]), (1 << 64) - 1)
                else:
                    self.assertEqual(case["status"], 0)
                    self.assertEqual(int(case["milliseconds"]), expected)
        self.assertGreater(overflow_cases, 0)


if __name__ == "__main__":
    unittest.main()
