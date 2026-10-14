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

    def test_wiki_only_configuration_can_lock(self):
        m.CONFIG.pop('root')
        m.CONFIG['wiki'] = {'root_node': 'home', 'space_id': 'space'}
        with m.local_lock():
            with self.assertRaises(RuntimeError):
                with m.local_lock():
                    self.fail('Concurrent Wiki writer acquired')

    def test_registered_peer_folder_read_and_write_scope(self):
        m.CONFIG.pop('root')
        m.CONFIG['drive_roots'] = {'project': {'token': 'folder', 'parent': 'cloud', 'access': 'write'}}
        m.CONFIG['documents']['project']['drive_root'] = 'project'
        inventory = {'cloud': [{'token': 'folder', 'type': 'folder', 'parent_token': 'cloud'}],
                     'folder': [{'token': 'doc', 'type': 'docx', 'parent_token': 'folder'}]}
        with patch.object(m, 'list_folder', side_effect=lambda token: iter(inventory[token])):
            m.check_location('project', write=True)
            self.assertEqual(m.search_scope(resource='project'), ('drive', ['--folder-tokens', 'folder']))
            m.CONFIG['drive_roots']['project']['access'] = 'read'
            m.check_location('project')
            with self.assertRaises(ValueError):
                m.check_location('project', write=True)
            inventory['cloud'] = []
            with self.assertRaises(ValueError):
                m.fetch('project')

    def test_search_never_falls_back_to_unscoped_drive(self):
        m.CONFIG.pop('root')
        m.CONFIG['wiki'] = {'space_id': 'space', 'root_node': 'home'}
        self.assertEqual(m.search_scope(), ('wiki', ['--space-ids', 'space']))
        for source, resource in [('memory', None), ('drive', None), ('drive', 'unknown'), ('wiki', 'project')]:
            with self.subTest(source=source, resource=resource), self.assertRaises(ValueError):
                m.search_scope(source, resource)

    def test_rootless_unregistered_drive_document_is_not_read(self):
        m.CONFIG.pop('root')
        with patch.object(m, 'cli') as cli, self.assertRaises(ValueError):
            m.fetch('project')
        cli.assert_not_called()

    def test_drive_cycle_and_unregistered_ancestor_fail(self):
        m.CONFIG['folders']['folder']['parent'] = 'folder'
        with self.assertRaises(ValueError):
            m.check_location('project')
        m.CONFIG['folders']['folder']['parent'] = 'unknown'
        with self.assertRaises(ValueError):
            m.check_location('project')

    def test_startup_reads_only_core_and_selected_overview(self):
        m.CONFIG.update(projects={'example': 'overview'}, topics={'network': 'network_overview'})
        def short_read(key, state, mode, budget):
            return {'key': key, 'content': 'x' * min(30, budget)}
        for project, topic, expected in [(None, None, 'navigation'), ('example', None, 'overview'),
                                          (None, 'network', 'network_overview')]:
            with self.subTest(project=project, topic=topic), patch.object(m, 'read', side_effect=short_read) as read:
                result = m.begin_context(self.path, project, topic)
                self.assertEqual([c.args[0] for c in read.call_args_list], ['core', expected])
                self.assertEqual(result['content_chars'], 60)
                self.assertEqual(result['budget'], 4000)

    def test_wiki_checks_full_registered_ancestry(self):
        m.CONFIG['wiki'] = {'space_id': 'space', 'root_node': 'home'}
        m.CONFIG['documents'].update({
            'home': {'token': 'home_doc', 'wiki_node': 'home', 'wiki_parent': 'space_root'},
            'overview': {'token': 'overview_doc', 'wiki_node': 'leaf', 'wiki_parent': 'home'}})
        leaf = {'space_id': 'space', 'node_token': 'leaf', 'obj_token': 'overview_doc',
                'obj_type': 'docx', 'node_type': 'origin', 'parent_node_token': 'home'}
        home = dict(leaf, node_token='home', obj_token='home_doc', parent_node_token='space_root')
        with patch.object(m, 'cli', side_effect=[{'data': leaf}, {'data': home}]) as cli:
            m.check_location('overview')
            self.assertEqual(cli.call_count, 2)
        for change in [{'parent_node_token': 'outside'}, {'space_id': 'other'},
                       {'node_type': 'shortcut'}, {'obj_token': 'other_doc'}]:
            with self.subTest(change=change), patch.object(m, 'cli', return_value={'data': dict(leaf, **change)}):
                with self.assertRaises(ValueError):
                    m.check_location('overview')

    def test_wiki_read_checks_location_before_fetching_content(self):
        m.CONFIG['documents']['project']['wiki_node'] = 'node'
        with patch.object(m, 'check_location', side_effect=ValueError('moved')), patch.object(m, 'cli') as cli:
            with self.assertRaises(ValueError):
                m.fetch('project')
            cli.assert_not_called()

    def test_wiki_cycle_fails(self):
        m.CONFIG['wiki'] = {'space_id': 'space', 'root_node': 'root'}
        m.CONFIG['documents']['project'].update(wiki_node='cycle', wiki_parent='cycle')
        node = {'space_id': 'space', 'node_token': 'cycle', 'obj_token': 'doc',
                'obj_type': 'docx', 'node_type': 'origin', 'parent_node_token': 'cycle'}
        with patch.object(m, 'cli', return_value={'data': node}):
            with self.assertRaises(ValueError):
                m.check_location('project')

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
