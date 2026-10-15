#!/usr/bin/env python3
"""Check global entry registration without using an account or network."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


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


if __name__ == '__main__':
    unittest.main(verbosity=2)
