import subprocess
import tempfile
import unittest
from pathlib import Path

import cerebramo


def cp(args, rc=0, out="", err=""):
    return subprocess.CompletedProcess(args=args, returncode=rc, stdout=out, stderr=err)


class CerebramoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        cerebramo.CONFIG_DIR = Path(self.tmp.name)
        cerebramo.CONFIG_FILE = cerebramo.CONFIG_DIR / "config.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_alias(self):
        self.assertEqual(cerebramo.normalize_provider("claude"), "anthropic")

    def test_order_round_trip(self):
        cerebramo.set_order(["claude", "minimax"])
        self.assertEqual(cerebramo.load_config()["provider_order"], ["anthropic", "minimax"])

    def test_failover(self):
        def runner(args):
            args = list(args)
            if args[:3] == ["opencode", "models", "anthropic"]:
                return cp(args, out="anthropic/claude-test\n")
            if args[:3] == ["opencode", "models", "minimax"]:
                return cp(args, out="minimax/m2-test\n")
            if args[:2] == ["opencode", "run"] and "anthropic/claude-test" in args:
                return cp(args, rc=1, err="quota exceeded")
            if args[:2] == ["opencode", "run"] and "minimax/m2-test" in args:
                return cp(args, out='{"ok":true}\n')
            return cp(args, rc=1, err="unexpected")

        cerebramo.set_order(["claude", "minimax"])
        rc, attempts, output = cerebramo.run_prompt("hola", runner=runner)
        self.assertEqual(rc, 0)
        self.assertEqual([x.provider for x in attempts], ["anthropic", "minimax"])
        self.assertFalse(attempts[0].ok)
        self.assertTrue(attempts[1].ok)
        self.assertIn('"ok":true', output)

    def test_set_model_requires_provider_prefix(self):
        with self.assertRaises(ValueError):
            cerebramo.set_model("claude", "minimax/foo")


if __name__ == "__main__":
    unittest.main()
