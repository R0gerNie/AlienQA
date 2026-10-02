"""Explicit opt-in build; all third-party files, caches and builds stay gitignored."""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tests/fixtures/framework-mechanisms'
WORKSPACE = ROOT / 'examples/open-source/t02-frameworks'


def prepare(install=False):
    import os
    env = {**os.environ, 'npm_config_cache': str(WORKSPACE / '.npm-cache'),
           'NEXT_TELEMETRY_DISABLED': '1', 'VITE_CJS_IGNORE_WARNING': 'true'}
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    for family in ('vite', 'next'):
        dest = WORKSPACE / family
        shutil.copytree(SOURCE / family, dest, dirs_exist_ok=True)
        if not (dest / 'package-lock.json').exists():
            raise RuntimeError('Versioned package-lock.json required')
        if install:
            subprocess.run(['npm', 'ci', '--no-audit', '--no-fund'], cwd=dest, env=env, check=True)
        subprocess.run(['npm', 'run', 'build'], cwd=dest, env=env, check=True)
    return WORKSPACE


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', action='store_true', help='Explicitly install locked dependencies in the ignored project workspace')
    args = parser.parse_args()
    print(prepare(args.install))
