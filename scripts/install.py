#!/usr/bin/env python3
"""Install the portable skill in the Codex skills directory."""

import argparse
import os
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-home', type=Path,
                        default=Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))))
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    target = args.codex_home.expanduser().resolve() / 'skills/feishu-memory'
    if target.resolve() != source:
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / 'SKILL.md', target / 'SKILL.md')
        for name in ('agents', 'scripts', 'references'):
            shutil.copytree(source / name, target / name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.local.json'))
    print(f'Installed: {target}')


if __name__ == '__main__':
    main()
