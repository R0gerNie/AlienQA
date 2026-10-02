"""Derive owned src/group/dynamic Next fixtures using the existing exact T02 lock.

No install or external clone. Dependencies are reused from the ignored T02
workspace; inputs, node_modules link, npm cache and output remain in this repo.
"""
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tests/fixtures/framework-mechanisms'
WORKSPACE = ROOT / 'examples/open-source/t01-frameworks'


def prepare():
    dest = WORKSPACE / 'apps/web'
    dependencies = ROOT / 'examples/open-source/t02-frameworks/next/node_modules'
    if not dependencies.is_dir():
        raise RuntimeError('First explicitly prepare T02 locked dependencies')
    dest.mkdir(parents=True, exist_ok=True)
    # Replace only this recipe's source directories, preventing root/src conflict.
    for name in ('app', 'pages', 'src'):
        if (dest / name).exists():
            shutil.rmtree(dest / name)
    for name in ('app', 'pages'):
        shutil.copytree(SOURCE / 'next' / name, dest / 'src' / name)
    for name in ('package.json', 'package-lock.json', 'next.config.js'):
        shutil.copy2(SOURCE / 'next' / name, dest / name)
    shutil.copytree(SOURCE / 'next-src', dest, dirs_exist_ok=True)
    link = dest / 'node_modules'
    if not link.exists():
        link.symlink_to(dependencies, target_is_directory=True)
    elif not link.is_symlink() or link.resolve() != dependencies.resolve():
        raise RuntimeError('Unexpected node_modules; use a clean T01 workspace')
    env = {**os.environ, 'NEXT_TELEMETRY_DISABLED': '1',
           'npm_config_cache': str(WORKSPACE / '.npm-cache')}
    subprocess.run(['npm', 'run', 'build'], cwd=dest, env=env, check=True)
    return WORKSPACE


if __name__ == '__main__':
    print(prepare())
