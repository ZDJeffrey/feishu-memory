#!/usr/bin/env python3
"""Check installation and mirror planning without using an account or network."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
import mirror  # noqa: E402


class Checks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def test_install_preserves_guidance_and_is_repeatable(self):
        home = self.path / 'codex'
        home.mkdir()
        guidance = home / 'AGENTS.md'
        override = home / 'AGENTS.override.md'
        original = b'Existing user guidance.\r\n'
        original_override = b'Override guidance.\n<!-- feishu-memory:start -->\nOld entry.\n<!-- feishu-memory:end -->\n'
        guidance.write_bytes(original)
        override.write_bytes(original_override)
        cmd = [sys.executable, str(Path(__file__).with_name('install.py')),
               '--codex-home', str(home)]
        for _ in range(2):
            subprocess.run(cmd, check=True, capture_output=True)
            self.assertEqual(guidance.read_bytes(), original)
            self.assertEqual(override.read_bytes(), original_override)
        self.assertTrue((home / 'skills/feishu-memory/SKILL.md').exists())
        self.assertFalse((home / 'skills/feishu-memory/references/resources.json').exists())
        self.assertFalse(list(home.glob('*.before-feishu-memory')))

    def test_help_and_retired_flags(self):
        script = str(Path(__file__).with_name('install.py'))
        help_result = subprocess.run([sys.executable, script, '--help'], capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0)
        self.assertNotIn('--activate', help_result.stdout)
        for flag in ('--activate', '--activate-only'):
            result = subprocess.run([sys.executable, script, '--codex-home', str(self.path / 'new'), flag],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((self.path / 'new').exists())


class MirrorPlan(unittest.TestCase):
    def node(self, token, title, parent='', obj=None):
        return {'node_token': token, 'title': title, 'parent_node_token': parent,
                'obj_token': obj or token + '-obj', 'obj_type': 'docx'}

    def test_layout_follows_tree_and_separates_duplicate_titles(self):
        nodes = [self.node('a', '项目'), self.node('b', '实验', 'a'), self.node('c', '实验', 'a'),
                 self.node('d', 'a/b: c', '')]
        paths = mirror.layout(nodes)
        self.assertEqual(paths['a'], '项目.md')
        self.assertEqual(paths['b'], '项目/实验.md')
        self.assertEqual(paths['c'], '项目/实验 (c).md')
        self.assertEqual(paths['d'], 'a_b_ c.md')

    def test_plan_reports_only_real_changes(self):
        nodes = [self.node('a', '概述'), self.node('b', '实验', 'a'), self.node('c', '设计', 'a')]
        paths = mirror.layout(nodes)
        times = {'a-obj': '1', 'b-obj': '2', 'c-obj': '3'}
        entries, changes, removed = mirror.plan({}, nodes, paths, times)
        self.assertEqual(sorted(k for k, _ in changes), ['new'] * 3)
        times['b-obj'] = '5'
        nodes[2]['title'] = '设计文档'
        old = dict(entries, z={'path': '旧.md', 'modified': '1'})
        _, changes, removed = mirror.plan(old, nodes, mirror.layout(nodes), times)
        self.assertEqual(sorted(changes), [('changed', 'b'), ('moved', 'c')])
        self.assertEqual(removed, ['z'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
