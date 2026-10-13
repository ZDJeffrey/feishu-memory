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


def find_cli(config):
    specified = os.environ.get('FEISHU_MEMORY_CLI') or config.get('cli')
    if specified:
        return shutil.which(str(Path(specified).expanduser()))
    return shutil.which('lark-cli') or shutil.which(str(Path.home() / '.local/bin/lark-cli'))


def doctor(config_path):
    config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
    binary = find_cli(config)
    result = {'config_path': str(config_path), 'cli_found': bool(binary),
              'config_found': bool(config), 'setup_guide': 'references/setup.md'}
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
    digest = hashlib.sha256((str(Path.home()) + CONFIG['root']).encode()).hexdigest()[:24]
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


def check_location(key):
    doc = CONFIG['documents'][key]
    chain = []
    parent = doc['parent']
    while parent != CONFIG['root']:
        above = CONFIG['folders'][parent]['parent']
        chain.append((above, parent, 'folder'))
        parent = above
    chain.reverse()
    chain.append((doc['parent'], doc['token'], 'docx'))
    for parent, token, kind in chain:
        match = next((item for item in list_folder(parent) if item['token'] == token), None)
        if not match or match['type'] != kind or match['parent_token'] != parent:
            raise ValueError('目标目录归属已变化；先核对远程入口和资源登记。')


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
        check_location(args.key)
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


def main():
    global CONFIG, CLI
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--state-dir', type=Path, default=Path('.feishu-memory'))
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    begin = sub.add_parser('begin')
    begin.add_argument('--project')
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
    writer = sub.add_parser('replace')
    writer.add_argument('key')
    for name in ('snapshot', 'block-id', 'xml', 'source'):
        writer.add_argument('--' + name, required=True)
    writer.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    args.config = args.config.expanduser().resolve()
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
    if args.command == 'begin':
        keys = ['core', 'navigation']
        if args.project:
            keys.append(CONFIG['projects'][args.project])
        docs, remaining = [], 12000
        for key in keys:
            doc = read(key, args.state_dir, 'full', budget=remaining)
            docs.append(doc)
            remaining -= len(doc['content'])
        output = {'documents': docs, 'content_chars': 12000 - remaining}
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
        command = ['drive', '+search', '--query', args.query, '--folder-tokens', CONFIG['root'],
                   '--doc-types', 'docx', '--page-size', '5']
        if args.only_title:
            command.append('--only-title')
        if args.page_token:
            command += ['--page-token', args.page_token]
        response = cli(*command)
        save(args.state_dir / 'search' / f'{uuid.uuid4().hex}.json', response)
        data = response['data']
        output = {'results': [{'title': re.sub(r'</?h[b]?>', '', r['title_highlighted']),
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
