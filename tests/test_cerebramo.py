import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_resource_round_trip_and_percentage(self):
        cerebramo.set_resource(
            "minehost.days",
            name="Minehost",
            category="hosting",
            available=12,
            maximum=30,
            unit="days",
            expires_at="2026-09-12",
            source="manual:minehost",
        )
        item = cerebramo.configured_resources()[0]
        self.assertEqual(item.id, "minehost.days")
        self.assertEqual(item.remaining_percent, 40.0)
        self.assertEqual(item.expires_at, "2026-09-12")

    def test_unknown_resource_does_not_invent_percentage(self):
        item = cerebramo.ResourceSnapshot(
            "claro.data", "Claro", "mobile", "unknown", source="claro:no-official-api"
        )
        self.assertIsNone(item.remaining_percent)

    def test_local_ram_and_uptime_collectors(self):
        base = Path(self.tmp.name)
        meminfo = base / "meminfo"
        uptime = base / "uptime"
        meminfo.write_text(
            "MemTotal: 1000 kB\nMemAvailable: 250 kB\nSwapTotal: 100 kB\nSwapFree: 50 kB\n"
        )
        uptime.write_text("86400.0 0.0\n")
        fake_disk = type("D", (), {"free": 25, "total": 100})()
        with patch("cerebramo.shutil.disk_usage", return_value=fake_disk), patch(
            "cerebramo.os.getloadavg", return_value=(0.5, 0.4, 0.3)
        ):
            items = cerebramo.collect_local_resources(
                meminfo_path=meminfo, uptime_path=uptime
            )
        by_id = {x.id: x for x in items}
        self.assertAlmostEqual(by_id["host.ram"].remaining_percent, 25.0)
        self.assertEqual(by_id["host.uptime"].available, 86400.0)
        self.assertAlmostEqual(by_id["host.disk"].remaining_percent, 25.0)

    def test_config_migrates_from_v1(self):
        cerebramo.CONFIG_FILE.write_text(
            json.dumps({"version": 1, "provider_order": ["minimax"], "models": {}})
        )
        cfg = cerebramo.load_config()
        self.assertEqual(cfg["version"], 2)
        self.assertEqual(cfg["resources"], {})


if __name__ == "__main__":
    unittest.main()
