#!/usr/bin/env python3
"""Install the portable skill; optionally activate its global task entry."""

import argparse
import os
from pathlib import Path
import shutil

START = '<!-- feishu-memory:start -->'
END = '<!-- feishu-memory:end -->'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-home', type=Path,
                        default=Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))))
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    home = args.codex_home.expanduser().resolve()
    target = home / 'skills/feishu-memory'
    if target.resolve() != source:
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / 'SKILL.md', target / 'SKILL.md')
        for name in ('agents', 'scripts', 'references'):
            shutil.copytree(source / name, target / name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.local.json'))
    if args.activate:
        guidance = home / 'AGENTS.md'
        original = guidance.read_text(encoding='utf-8') if guidance.exists() else ''
        block = (f'{START}\n'
                 '科研、开发、写作、环境操作、项目接续及记忆维护任务，'
                 f'先读取 `{target / "SKILL.md"}` 并按需取得远程上下文；'
                 '任务收尾按该技能更新项目状态和可复用记忆。'
                 '自包含的简单请求可直接处理，同一会话复用已读准则。\n'
                 f'{END}')
        if START in original:
            start, end = original.index(START), original.index(END) + len(END)
            updated = original[:start] + block + original[end:]
        else:
            updated = original.rstrip() + '\n\n' + block + '\n'
        if updated != original:
            if guidance.exists():
                shutil.copy2(guidance, guidance.with_name('AGENTS.md.before-feishu-memory'))
            guidance.write_text(updated, encoding='utf-8')
        print(f'Activated: {guidance}')
        if (home / 'AGENTS.override.md').exists():
            print('AGENTS.override.md exists; add the same entry there if it is the active global instruction file.')
    print(f'Installed: {target}')


if __name__ == '__main__':
    main()
