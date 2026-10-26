"""Tests for install_skill.py that need no network: python3 -m unittest discover -s tests"""
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "skills/inhale/scripts/install_skill.py"


def run(*args):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True)


class Commit(unittest.TestCase):
    def test_commit_must_be_a_full_sha_and_is_checked_before_cloning(self):
        for bad in ("abc1234", "x" * 40, "A" * 40, ""):
            r = run("o/r", "skill", "--scope", "user", "--commit", bad)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("--commit needs a full 40-character sha", r.stderr)


if __name__ == "__main__":
    unittest.main()
