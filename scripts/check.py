#!/usr/bin/env python3
"""Check installation and mirror planning without using an account or network."""

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import mirror  # noqa: E402


class Checks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def test_install_preserves_guidance_and_is_repeatable(self):
        home = self.path / "codex"
        home.mkdir()
        guidance = home / "AGENTS.md"
        override = home / "AGENTS.override.md"
        original = b"Existing user guidance.\r\n"
        original_override = (
            b"Override guidance.\n<!-- feishu-memory:start -->\nOld entry.\n<!-- feishu-memory:end -->\n"
        )
        guidance.write_bytes(original)
        override.write_bytes(original_override)
        cmd = [sys.executable, str(Path(__file__).with_name("install.py")), "--codex-home", str(home)]
        for _ in range(2):
            subprocess.run(cmd, check=True, capture_output=True)
            self.assertEqual(guidance.read_bytes(), original)
            self.assertEqual(override.read_bytes(), original_override)
        self.assertTrue((home / "skills/feishu-memory/SKILL.md").exists())
        self.assertFalse((home / "skills/feishu-memory/references/resources.json").exists())
        self.assertFalse(list(home.glob("*.before-feishu-memory")))

    def test_help_and_retired_flags(self):
        script = str(Path(__file__).with_name("install.py"))
        help_result = subprocess.run([sys.executable, script, "--help"], capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0)
        self.assertNotIn("--activate", help_result.stdout)
        for flag in ("--activate", "--activate-only"):
            result = subprocess.run(
                [sys.executable, script, "--codex-home", str(self.path / "new"), flag], capture_output=True, text=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((self.path / "new").exists())


class MirrorPlan(unittest.TestCase):
    def node(self, token, title, parent="", obj=None):
        return {
            "node_token": token,
            "title": title,
            "parent_node_token": parent,
            "obj_token": obj or token + "-obj",
            "obj_type": "docx",
        }

    def test_layout_follows_tree_and_separates_duplicate_titles(self):
        nodes = [
            self.node("a", "项目"),
            self.node("b", "实验", "a"),
            self.node("c", "实验", "a"),
            self.node("d", "a/b: c", ""),
        ]
        paths = mirror.layout(nodes)
        self.assertEqual(paths["a"], "项目.md")
        self.assertEqual(paths["b"], "项目/实验.md")
        self.assertEqual(paths["c"], "项目/实验 (c).md")
        self.assertEqual(paths["d"], "a_b_ c.md")

    def test_plan_reports_only_real_changes(self):
        nodes = [self.node("a", "概述"), self.node("b", "实验", "a"), self.node("c", "设计", "a")]
        paths = mirror.layout(nodes)
        times = {"a-obj": "1", "b-obj": "2", "c-obj": "3"}
        entries, changes, removed = mirror.plan({}, nodes, paths, times)
        self.assertEqual(sorted(k for k, _ in changes), ["new"] * 3)
        times["b-obj"] = "5"
        nodes[2]["title"] = "设计文档"
        old = dict(entries, z={"path": "旧.md", "modified": "1"})
        _, changes, removed = mirror.plan(old, nodes, mirror.layout(nodes), times)
        self.assertEqual(sorted(changes), [("changed", "b"), ("moved", "c")])
        self.assertEqual(removed, ["z"])


class WorkingCopy(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mirror_root = self.root / "mirror"
        (self.mirror_root / "docs").mkdir(parents=True)
        self.entry = {"title": "设计", "path": "设计.md", "obj": "obj", "type": "docx", "revision": 3}
        (self.mirror_root / "manifest.json").write_text(json.dumps({"nodes": {"node": self.entry}}))
        self.source = self.mirror_root / "docs" / self.entry["path"]
        self.source.write_text('---\ntitle: 设计\n---\n\n正文\n<whiteboard token="board1"></whiteboard>\n')
        self.mirror = mirror.Mirror(
            {"wiki": {"space_id": "space", "url": "https://example.com/wiki/root"}, "profile": "test"}, self.mirror_root
        )

    def checkout(self, query="node"):
        output = io.StringIO()
        with patch("mirror.tempfile.mkdtemp", return_value=str(self.root / "work")), redirect_stdout(output):
            (self.root / "work").mkdir()
            self.mirror.checkout(query)
        return Path(output.getvalue().strip())

    def status(self, work):
        output = io.StringIO()
        with redirect_stdout(output):
            self.mirror.work_status(work)
        return output.getvalue()

    def test_checkout_is_independent_and_tracks_resource_changes(self):
        work = self.checkout()
        baseline = (work / "baseline.md").read_text()
        self.assertIn("[飞书画板 board1](assets/board1/description.md)", baseline)
        self.assertIn("尚未导出", (work / "assets/board1/description.md").read_text())
        task = json.loads((work / "task.json").read_text())
        self.assertEqual(task["resources"][0]["original"], '<whiteboard token="board1"></whiteboard>')
        self.source.write_text("更新后的镜像")
        self.assertEqual((work / "working.md").read_text(), baseline)
        self.assertIn("mirror: changed", self.status(work))
        (work / "working.md").write_text(baseline.replace("board1", "board2"))
        self.assertIn("whiteboard references changed", self.status(work))
        (work / "working.md").write_text(baseline + baseline)
        self.assertIn("whiteboard references changed", self.status(work))

    def test_baseline_tampering_and_ambiguous_page(self):
        work = self.checkout()
        (work / "baseline.md").write_text("changed")
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()):
            self.mirror.work_status(work)
        self.mirror.manifest["nodes"]["other"] = dict(self.entry, obj="obj2")
        with self.assertRaises(SystemExit):
            self.mirror.checkout("设计")

    def test_code_fence_does_not_turn_example_into_resource(self):
        text = '```xml\n<whiteboard token="example"></whiteboard>\n```\n'
        self.assertEqual(mirror.work_view(text), (text, []))

    def test_invalid_resource_token_stays_in_document(self):
        text = '<whiteboard token="../../outside"></whiteboard>\n'
        self.source.write_text(text)
        work = self.checkout()
        self.assertEqual((work / "working.md").read_text(), text)
        self.assertFalse((work / "assets").exists())
        self.assertFalse((self.root / "outside").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
