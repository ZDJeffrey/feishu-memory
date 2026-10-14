#!/usr/bin/env python3
"""Read scoped Feishu memory and replace observed text blocks with receipts."""

import argparse
import datetime as dt
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET

CONFIG = {}
CLI = None
DEFAULT_CONFIG = Path(os.environ.get('FEISHU_MEMORY_CONFIG',
                                    str(Path.home() / '.config/feishu-memory/config.json')))
DEFAULT_STATE_DIR = Path.home() / '.local/state/feishu-memory'


def find_cli(config):
    specified = os.environ.get('FEISHU_MEMORY_CLI') or config.get('cli')
    if specified:
        return shutil.which(str(Path(specified).expanduser()))
    return shutil.which('lark-cli') or shutil.which(str(Path.home() / '.local/bin/lark-cli'))


def doctor(config_path):
    config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
    binary = find_cli(config)
    result = {'config_path': str(config_path), 'cli_found': bool(binary),
              'config_found': bool(config), 'resources_verified': False,
              'setup_guide': 'references/setup.md'}
    if not binary or not config:
        result['status'] = 'setup_required'
        return result
    check = subprocess.run([binary, '--profile', config['profile'], 'auth', 'status', '--json', '--verify'],
                           capture_output=True, text=True, encoding='utf-8', timeout=90)
    if check.returncode:
        result.update(status='authentication_required', detail=check.stderr.strip())
        return result
    auth = json.loads(check.stdout)
    user = auth.get('identities', {}).get('user', {})
    ready = user.get('verified') is True and user.get('status') == 'ready'
    result.update(status='ready' if ready else 'authentication_required',
                  identity='user', verified=ready, token_status=user.get('tokenStatus'))
    return result


@contextmanager
def local_lock():
    namespace = CONFIG['wiki']['root_node']
    digest = hashlib.sha256((str(Path.home()) + namespace).encode()).hexdigest()[:24]
    path = Path(tempfile.gettempdir()) / f'feishu-memory-{digest}.lock'
    with path.open('a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0)
            lock.write(b'0')
            lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise RuntimeError('Another local memory writer is active; reread after it finishes.') from None
        else:
            import fcntl
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Another local memory writer is active; reread after it finishes.') from None
        try:
            yield
        finally:
            if os.name == 'nt':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def cli(*args, content=None):
    result = subprocess.run(
        [CLI, '--profile', CONFIG['profile'], *args, '--as', 'user'],
        input=content, capture_output=True, text=True, encoding='utf-8', timeout=90,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    response = json.loads(result.stdout)
    if not response.get('ok'):
        raise RuntimeError(json.dumps(response, ensure_ascii=False))
    return response


def xml_root(content):
    return ET.fromstring('<root>' + content + '</root>')


def signature(element):
    attrs = tuple(sorted((k, v) for k, v in element.attrib.items()
                         if k not in {'id', 'seq', 'seq-marker'}))
    return (element.tag, attrs, element.text or '',
            tuple((signature(child), child.tail or '') for child in element))


def fetch(key, **scope):
    check_location(key)
    args = ['docs', '+fetch', '--doc', CONFIG['documents'][key]['token'], '--detail', 'full']
    for name, value in scope.items():
        args += ['--' + name.replace('_', '-'), str(value)]
    return cli(*args)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def read(key, state, mode='outline', value=None, budget=12000):
    scope = {} if mode == 'full' else {'scope': mode}
    if mode == 'section':
        outline = fetch(key, scope='outline')
        root = xml_root(outline['data']['document']['content'])
        headings = [e for e in root.iter() if re.fullmatch(r'h[1-9]', e.tag)
                    and ''.join(e.itertext()) == value]
        if len(headings) != 1:
            raise ValueError('章节标题须唯一匹配；先读取 outline 定位。')
        scope['start_block_id'] = headings[0].attrib['id']
    if mode == 'keyword':
        scope['keyword'] = value
    response = fetch(key, **scope)
    doc = response['data']['document']
    path = state / 'snapshots' / f'{key}-{doc["revision_id"]}-{uuid.uuid4().hex[:8]}.json'
    save(path, {'key': key, 'response': response})
    content = doc['content']
    limited = len(content) > budget
    if limited:
        content = fetch(key, scope='outline')['data']['document']['content']
        if len(content) > budget:
            content = ''
    return {'key': key, 'url': CONFIG['documents'][key]['url'],
            'revision': doc['revision_id'], 'snapshot': str(path.resolve()),
            'requested_scope': mode, 'outline_only': limited,
            'content': content,
            'next': '用 section 或 keyword 缩小范围。' if limited else None}


def list_folder(folder):
    params = {'folder_token': folder, 'page_size': 200}
    while True:
        data = cli('drive', 'files', 'list', '--params', json.dumps(params))['data']
        yield from data['files']
        if not data.get('has_more'):
            return
        params['page_token'] = data['next_page_token']


def check_drive_root(key, write=False):
    resource = CONFIG.get('drive_roots', {}).get(key)
    if not resource or resource.get('access') not in {'read', 'write'}:
        raise ValueError('Drive 资料根目录未启用；先核对资源索引。')
    if write and resource['access'] != 'write':
        raise ValueError('此 Drive 资料目录仅允许读取。')
    match = next((item for item in list_folder(resource['parent'])
                  if item['token'] == resource['token']), None)
    if not match or match['type'] != 'folder' or match['parent_token'] != resource['parent']:
        raise ValueError('Drive 资料根目录位置已变化；先核对资源索引。')
    return resource['token']


def check_location(key, write=False):
    doc = CONFIG['documents'][key]
    if doc.get('wiki_node'):
        wiki = CONFIG['wiki']
        registered = {d['wiki_node']: d for d in CONFIG['documents'].values() if d.get('wiki_node')}
        node, visited = doc['wiki_node'], set()
        while node:
            if node in visited or node not in registered:
                raise ValueError('Wiki 目录链未登记或存在循环。')
            visited.add(node)
            expected = registered[node]
            actual = cli('wiki', '+node-get', '--node-token', node,
                         '--space-id', wiki['space_id'])['data']
            if (actual['space_id'] != wiki['space_id'] or actual['node_token'] != node
                    or actual['obj_token'] != expected['token'] or actual['obj_type'] != 'docx'
                    or actual['node_type'] != 'origin'
                    or actual.get('parent_node_token', '') != expected['wiki_parent']):
                raise ValueError('Wiki 节点归属、类型或内容对象已变化；先核对资源登记。')
            if node == wiki['root_node']:
                return
            node = expected['wiki_parent']
        raise ValueError('Wiki 节点不属于已登记的入口子树。')
    if not doc.get('drive_root'):
        raise ValueError('Drive 文档未登记资料根目录。')
    root = check_drive_root(doc['drive_root'], write)
    chain, visited = [], set()
    parent = doc['parent']
    while parent != root:
        if parent in visited or parent not in CONFIG.get('folders', {}):
            raise ValueError('Drive 目录链未登记或存在循环。')
        visited.add(parent)
        above = CONFIG['folders'][parent]['parent']
        chain.append((above, parent, 'folder'))
        parent = above
    chain.reverse()
    chain.append((doc['parent'], doc['token'], 'docx'))
    for parent, token, kind in chain:
        match = next((item for item in list_folder(parent) if item['token'] == token), None)
        if not match or match['type'] != kind or match['parent_token'] != parent:
            raise ValueError('目标目录归属已变化；先核对远程入口和资源登记。')


def begin_context(state, project=None, topic=None):
    selected = (CONFIG['projects'][project] if project else
                CONFIG.get('topics', {})[topic] if topic else 'navigation')
    budget = CONFIG.get('startup_budget', 4000)
    if not isinstance(budget, int) or budget < 1:
        raise ValueError('startup_budget 必须为正整数。')
    docs, remaining = [], budget
    for key in dict.fromkeys(['core', selected]):
        doc = read(key, state, 'full', budget=remaining)
        docs.append(doc)
        remaining -= len(doc['content'])
    return {'documents': docs, 'content_chars': budget - remaining, 'budget': budget}


def browse(key, page_token=None):
    doc = CONFIG['documents'][key]
    if not doc.get('wiki_node'):
        raise ValueError('browse 需要已登记的 Wiki 页面。')
    check_location(key)
    command = ['wiki', '+node-list', '--space-id', CONFIG['wiki']['space_id'],
               '--parent-node-token', doc['wiki_node'], '--page-size', '5']
    if page_token:
        command += ['--page-token', page_token]
    data = cli(*command)['data']
    keys = {d['wiki_node']: k for k, d in CONFIG['documents'].items() if d.get('wiki_node')}
    return {'parent': key, 'nodes': [
        {'key': keys.get(n['node_token']), 'title': n['title'], 'node_token': n['node_token'],
         'type': n['obj_type'], 'node_type': n['node_type'], 'has_child': n.get('has_child', False)}
        for n in data.get('nodes', [])], 'has_more': data.get('has_more', False),
        'page_token': data.get('page_token')}


def replace(args, state):
    observed = json.loads(Path(args.snapshot).read_text(encoding='utf-8'))
    if observed['key'] != args.key:
        raise ValueError('快照与写入目标不一致。')
    before = observed['response']['data']['document']
    if before['document_id'] != CONFIG['documents'][args.key]['token']:
        raise ValueError('快照中的文档标识不匹配。')
    blocks = [e for e in xml_root(before['content']).iter() if e.get('id') == args.block_id]
    if len(blocks) != 1:
        raise ValueError('目标块须出现在本次读取快照中。')
    old = blocks[0]
    new = ET.fromstring(Path(args.xml).read_text(encoding='utf-8').strip())
    if new.tag not in {'p', 'li', 'h1', 'h2', 'h3', 'h4'} or new.tag != old.tag:
        raise ValueError('此入口替换同类型的段落、列表项或标题；其他结构使用 lark-doc。')
    allowed = {'p', 'li', 'h1', 'h2', 'h3', 'h4', 'a', 'b', 'em', 'u', 'del', 'span', 'br'}
    if any(e.tag not in allowed for e in new.iter()) or any(e.tag not in allowed for e in old.iter()):
        raise ValueError('含资源或复杂子块的内容使用 lark-doc 保真编辑。')
    for e in new.iter():
        e.attrib.pop('id', None)
        e.attrib.pop('seq-marker', None)
    with local_lock():
        check_location(args.key, write=True)
        latest = fetch(args.key, scope='outline')['data']['document']
        if latest['revision_id'] != before['revision_id']:
            return {'status': 'conflict', 'expected_revision': before['revision_id'],
                    'actual_revision': latest['revision_id'], 'written': False}
        current = fetch(args.key, scope='range', start_block_id=args.block_id, end_block_id=args.block_id)
        current_doc = current['data']['document']
        if current_doc['revision_id'] != before['revision_id']:
            return {'status': 'conflict', 'expected_revision': before['revision_id'],
                    'actual_revision': current_doc['revision_id'], 'written': False}
        live = [e for e in xml_root(current_doc['content']).iter() if e.get('id') == args.block_id]
        if len(live) != 1 or signature(live[0]) != signature(old):
            return {'status': 'conflict', 'reason': '目标内容已变化', 'written': False}
        if signature(live[0]) == signature(new):
            return {'status': 'unchanged', 'revision': before['revision_id'], 'written': False}
        receipt = {'key': args.key, 'source': args.source, 'block_id': args.block_id,
                   'base_revision': before['revision_id'], 'snapshot': str(Path(args.snapshot).resolve()),
                   'before_xml': ET.tostring(old, encoding='unicode'),
                   'after_xml': ET.tostring(new, encoding='unicode'),
                   'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                   'status': 'prepared'}
        path = state / 'receipts' / f'{uuid.uuid4().hex}.json'
        save(path, receipt)
        if args.dry_run:
            return {'written': False, 'receipt': str(path.resolve()), **receipt}
        receipt['status'] = 'write_requested'
        save(path, receipt)
        result = cli('docs', '+update', '--doc', before['document_id'], '--command', 'block_replace',
                     '--block-id', args.block_id, '--revision-id', str(before['revision_id']),
                     '--content', '-', content=receipt['after_xml'])
        receipt['write_response'] = result
        receipt['status'] = 'readback_required'
        save(path, receipt)
        after = fetch(args.key)
        receipt['readback'] = after
        candidates = xml_root(after['data']['document']['content'])
        matched = any(signature(e) == signature(new) for e in candidates.iter())
        data = result['data']
        successful = data.get('result') == 'success' and not data.get('warnings') and matched
        receipt['status'] = 'verified' if successful else 'review_required'
        receipt['revision'] = after['data']['document']['revision_id']
        save(path, receipt)
        if not successful:
            raise RuntimeError(f'写入后需要核对回执：{path.resolve()}')
        return {'status': 'verified', 'written': True, 'revision': receipt['revision'],
                'receipt': str(path.resolve()), 'url': CONFIG['documents'][args.key]['url']}


def search_scope(source=None, resource=None):
    source = source or ('drive' if resource else 'wiki')
    if resource and source != 'drive':
        raise ValueError('--resource 只与 Drive 搜索一起使用。')
    if source == 'wiki':
        if not CONFIG.get('wiki'):
            raise ValueError('Wiki 尚未登记。')
        return source, ['--space-ids', CONFIG['wiki']['space_id']]
    if source == 'drive':
        if not resource:
            raise ValueError('Drive 搜索须用 --resource 指定已登记资料目录。')
        return source, ['--folder-tokens', check_drive_root(resource)]
    raise ValueError('搜索来源须为 wiki 或 drive。')


def main():
    global CONFIG, CLI
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--state-dir', type=Path, default=DEFAULT_STATE_DIR,
                        help='State directory (default: ~/.local/state/feishu-memory).')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    begin = sub.add_parser('begin')
    selection = begin.add_mutually_exclusive_group()
    selection.add_argument('--project')
    selection.add_argument('--topic')
    browser = sub.add_parser('browse')
    browser.add_argument('key', nargs='?', default='navigation')
    browser.add_argument('--page-token')
    reader = sub.add_parser('read')
    reader.add_argument('key')
    modes = reader.add_mutually_exclusive_group()
    modes.add_argument('--full', action='store_true')
    modes.add_argument('--section')
    modes.add_argument('--keyword')
    search = sub.add_parser('search')
    search.add_argument('query')
    search.add_argument('--only-title', action='store_true')
    search.add_argument('--page-token')
    search.add_argument('--source', choices=['wiki', 'drive'])
    search.add_argument('--resource', help='Registered drive_roots key; selects Drive search.')
    writer = sub.add_parser('replace')
    writer.add_argument('key')
    for name in ('snapshot', 'block-id', 'xml', 'source'):
        writer.add_argument('--' + name, required=True)
    writer.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    args.config = args.config.expanduser().resolve()
    args.state_dir = args.state_dir.expanduser().resolve()
    if args.command == 'doctor':
        print(json.dumps(doctor(args.config), ensure_ascii=False, indent=2))
        return 0
    if not args.config.is_file():
        raise ValueError('Memory configuration is missing. Read references/setup.md, then run doctor.')
    CONFIG = json.loads(args.config.read_text(encoding='utf-8'))
    CLI = find_cli(CONFIG)
    if not CLI:
        raise ValueError('lark-cli is missing. Follow the official larksuite/cli README via references/setup.md.')
    if getattr(args, 'key', None) and args.key not in CONFIG['documents']:
        raise ValueError('Unknown document key. Register it in the local configuration after checking its folder.')
    if getattr(args, 'project', None) and args.project not in CONFIG['projects']:
        raise ValueError('Unknown project. Read the remote navigation document and register the project.')
    if getattr(args, 'topic', None) and args.topic not in CONFIG.get('topics', {}):
        raise ValueError('Unknown topic. Read the Wiki learning index and register the topic.')
    if args.command == 'begin':
        output = begin_context(args.state_dir, args.project, args.topic)
    elif args.command == 'browse':
        output = browse(args.key, args.page_token)
    elif args.command == 'read':
        mode, value = ('full', None) if args.full else ('outline', None)
        if args.section:
            mode, value = 'section', args.section
        if args.keyword:
            mode, value = 'keyword', args.keyword
        output = read(args.key, args.state_dir, mode, value)
    elif args.command == 'search':
        if not args.query.strip() or len(args.query) > 30:
            raise ValueError('搜索使用 1–30 个字符的实体或主题词。')
        source, scope = search_scope(args.source, args.resource)
        command = ['drive', '+search', '--query', args.query, *scope, '--page-size', '5']
        if args.only_title:
            command.append('--only-title')
        if args.page_token:
            command += ['--page-token', args.page_token]
        response = cli(*command)
        save(args.state_dir / 'search' / f'{uuid.uuid4().hex}.json', response)
        data = response['data']
        output = {'source': source, 'results': [{'title': re.sub(r'</?h[b]?>', '', r['title_highlighted']),
                    'summary': r.get('summary_highlighted', ''),
                    'token': r['result_meta']['token'], 'url': r['result_meta']['url']}
                    for r in data.get('results', [])],
                  'has_more': data.get('has_more', False), 'page_token': data.get('page_token')}
    else:
        output = replace(args, args.state_dir)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if output.get('status') == 'conflict':
        return 2
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
