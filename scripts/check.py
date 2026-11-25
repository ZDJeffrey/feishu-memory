#!/usr/bin/env python3
"""Check installation and lazy mirror planning without using an account or network."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
        original_override = b"Override guidance.\n"
        guidance.write_bytes(original)
        override.write_bytes(original_override)
        cmd = [sys.executable, str(Path(__file__).with_name("install.py")), "--codex-home", str(home)]
        for _ in range(2):
            subprocess.run(cmd, check=True, capture_output=True)
            self.assertEqual(guidance.read_bytes(), original)
            self.assertEqual(override.read_bytes(), original_override)
        self.assertTrue((home / "skills/feishu-memory/SKILL.md").exists())
        self.assertFalse((home / "skills/feishu-memory/references/resources.json").exists())

    def test_help_and_retired_flags(self):
        script = str(Path(__file__).with_name("install.py"))
        help_result = subprocess.run([sys.executable, script, "--help"], capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0)
        self.assertNotIn("--activate", help_result.stdout)


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

    def test_core_scope_and_tree_rendering(self):
        self.assertTrue(mirror.is_core_path("知识与协作入口.md"))
        self.assertTrue(mirror.is_core_path("知识与协作入口/核心协作准则 · 摘要.md"))
        self.assertTrue(mirror.is_core_path("知识与协作入口/Agent 记忆/写作规范.md"))
        self.assertFalse(mirror.is_core_path("论文/每日导读/2026-11-25.md"))
        self.assertTrue(mirror.matches_scope("模型推理优化实践/Hy-image3.5.md", ["模型推理优化实践"]))
        self.assertFalse(mirror.matches_scope("TorchOmni/背景.md", ["模型推理优化实践"]))
        with tempfile.TemporaryDirectory() as td:
            docs = Path(td)
            (docs / "a.md").write_text("hi", encoding="utf-8")
            entries = {
                "1": {"path": "a.md", "type": "docx", "modified": "10", "cached_modified": "10"},
                "2": {"path": "b.md", "type": "docx", "modified": "20", "cached_modified": ""},
            }
            tree = mirror.render_tree(entries, docs)
            self.assertIn("`a.md` [cached]", tree)
            self.assertIn("`b.md` [remote]", tree)


if __name__ == "__main__":
    unittest.main(verbosity=2)
