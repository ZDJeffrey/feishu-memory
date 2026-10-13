#!/usr/bin/env python3
"""Exercise memory write invariants without using an account or network."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('memory', Path(__file__).with_name('memory.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def response(revision, content):
    return {'ok': True, 'data': {'document': {'document_id': 'doc', 'revision_id': revision,
                                             'content': content}}}


class Checks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        m.CONFIG = {'root': 'root', 'profile': 'memory', 'folders': {'folder': {'parent': 'root'}},
                    'documents': {'project': {'token': 'doc', 'parent': 'folder', 'url': 'https://example.test/doc'}}}
        self.snapshot = self.path / 'snapshot.json'
        m.save(self.snapshot, {'key': 'project', 'response': response(4, '<p id="block">old</p>')})
        self.content = self.path / 'new.xml'
        self.content.write_text('<p>new</p>')
        self.args = SimpleNamespace(key='project', snapshot=str(self.snapshot), block_id='block',
                                    xml=str(self.content), source='local check fixture', dry_run=False)

    def test_missing_installation_routes_to_setup(self):
        with patch.object(m, 'find_cli', return_value=None):
            result = m.doctor(self.path / 'absent.json')
        self.assertEqual(result['status'], 'setup_required')
        self.assertFalse(result['config_found'])

    def test_read_budget_returns_outline(self):
        with patch.object(m, 'fetch', side_effect=[response(4, '<p>' + 'x' * 300 + '</p>'),
                                                    response(4, '<h1>Topic</h1>')]):
            result = m.read('project', self.path, 'full', budget=100)
        self.assertTrue(result['outline_only'])
        self.assertLessEqual(len(result['content']), 100)
        self.assertIn('x' * 300, json.loads(Path(result['snapshot']).read_text())['response']['data']['document']['content'])

    def test_outside_location_stops_write(self):
        with patch.object(m, 'list_folder', return_value=iter([])), patch.object(m, 'cli') as cli:
            with self.assertRaises(ValueError):
                m.replace(self.args, self.path)
        cli.assert_not_called()

    def test_stale_version_stops_write(self):
        with patch.object(m, 'check_location'), patch.object(m, 'fetch', return_value=response(5, '')):
            with patch.object(m, 'cli') as cli:
                result = m.replace(self.args, self.path)
        self.assertEqual(result['status'], 'conflict')
        cli.assert_not_called()

    def test_duplicate_content_skips_write(self):
        self.content.write_text('<p>old</p>')
        with patch.object(m, 'check_location'), patch.object(m, 'fetch', return_value=response(4, '<p id="block">old</p>')):
            with patch.object(m, 'cli') as cli:
                result = m.replace(self.args, self.path)
        self.assertEqual(result['status'], 'unchanged')
        cli.assert_not_called()

    def test_different_live_content_stops_write(self):
        with patch.object(m, 'check_location'), patch.object(m, 'fetch', return_value=response(4, '<p id="block">changed</p>')):
            with patch.object(m, 'cli') as cli:
                result = m.replace(self.args, self.path)
        self.assertEqual(result['status'], 'conflict')
        cli.assert_not_called()

    def test_write_requires_readback(self):
        live = response(4, '<p id="block">old</p>')
        update = {'ok': True, 'data': {'result': 'success', 'warnings': []}}
        for actual, expected in [('new', 'verified'), ('different', 'review_required')]:
            with self.subTest(actual=actual), patch.object(m, 'check_location'):
                with patch.object(m, 'fetch', side_effect=[live, live, response(5, f'<p id="next">{actual}</p>')]):
                    with patch.object(m, 'cli', return_value=update):
                        if expected == 'verified':
                            result = m.replace(self.args, self.path)
                            self.assertEqual(result['status'], expected)
                        else:
                            with self.assertRaises(RuntimeError):
                                m.replace(self.args, self.path)
        receipts = [json.loads(p.read_text()) for p in (self.path / 'receipts').glob('*.json')]
        self.assertEqual({r['status'] for r in receipts}, {'verified', 'review_required'})

    def test_single_local_writer(self):
        with m.local_lock():
            with self.assertRaises(RuntimeError):
                with m.local_lock():
                    self.fail('Concurrent lock acquired')

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


if __name__ == '__main__':
    unittest.main(verbosity=2)
