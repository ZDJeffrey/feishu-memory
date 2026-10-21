#!/usr/bin/env python3
"""Check entry registration and mirror planning without using an account or network."""

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
        guidance.write_text('Existing user guidance.\n')
        cmd = [sys.executable, str(Path(__file__).with_name('install.py')),
               '--codex-home', str(home), '--activate']
        subprocess.run(cmd, check=True, capture_output=True)
        first = guidance.read_text()
        subprocess.run(cmd, check=True, capture_output=True)
        self.assertEqual(first, guidance.read_text())
        self.assertTrue(first.startswith('Existing user guidance.\n'))
        self.assertEqual(first.count('<!-- feishu-memory:start -->'), 1)
        self.assertFalse((home / 'skills/feishu-memory/references/resources.json').exists())

    def test_activation_uses_existing_skill_without_copying(self):
        home = self.path / 'new-codex-home'
        script = Path(__file__).with_name('install.py').resolve()
        cmd = [sys.executable, str(script), '--codex-home', str(home), '--activate-only']
        subprocess.run(cmd, check=True, capture_output=True)
        guidance = home / 'AGENTS.md'
        first = guidance.read_text()
        self.assertIn(str(script.parents[1] / 'SKILL.md'), first)
        self.assertFalse((home / 'skills').exists())
        subprocess.run(cmd, check=True, capture_output=True)
        self.assertEqual(first, guidance.read_text())

    def test_activation_preserves_and_updates_effective_override(self):
        home = self.path / 'codex'
        home.mkdir()
        base = home / 'AGENTS.md'
        base.write_text('Base guidance.\n')
        override = home / 'AGENTS.override.md'
        original = ('Override guidance.\n<!-- feishu-memory:start -->\n'
                    'Outdated entry.\n<!-- feishu-memory:end -->\nTrailing guidance.\n')
        override.write_text(original)
        script = Path(__file__).with_name('install.py').resolve()
        subprocess.run([sys.executable, str(script), '--codex-home', str(home),
                        '--activate-only'], check=True, capture_output=True)
        updated = override.read_text()
        self.assertEqual(base.read_text(), 'Base guidance.\n')
        self.assertTrue(updated.startswith('Override guidance.\n'))
        self.assertTrue(updated.endswith('\nTrailing guidance.\n'))
        self.assertEqual(updated.count('<!-- feishu-memory:start -->'), 1)
        self.assertIn(str(script.parents[1] / 'SKILL.md'), updated)
        self.assertEqual(override.with_name(override.name + '.before-feishu-memory').read_text(), original)

    def test_empty_override_keeps_base_guidance_active(self):
        home = self.path / 'codex'
        home.mkdir()
        base = home / 'AGENTS.md'
        base.write_text('Existing user guidance.\n')
        override = home / 'AGENTS.override.md'
        override.write_text('')
        subprocess.run([sys.executable, str(Path(__file__).with_name('install.py')),
                        '--codex-home', str(home), '--activate-only'], check=True, capture_output=True)
        self.assertEqual(override.read_text(), '')
        self.assertTrue(base.read_text().startswith('Existing user guidance.\n'))
        self.assertIn('<!-- feishu-memory:start -->', base.read_text())


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
