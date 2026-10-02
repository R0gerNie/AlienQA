"""Explicit pinned upstream sample preparation; external files remain gitignored."""
import argparse
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
WORKSPACE=ROOT/'examples/open-source/t09-todomvc'
COMMIT='ff43b02e59dfa604386bb382034b2cd07c2bcd8a'
UPSTREAM='https://github.com/tastejs/todomvc.git'


def prepare(install=False):
    if not WORKSPACE.exists():
        subprocess.run(['git','clone','--filter=blob:none','--no-checkout','--sparse',UPSTREAM,str(WORKSPACE)],check=True)
        subprocess.run(['git','-C',str(WORKSPACE),'sparse-checkout','set','examples/react','bower_components'],check=True)
        subprocess.run(['git','-C',str(WORKSPACE),'checkout','--detach',COMMIT],check=True)
    actual=subprocess.check_output(['git','-C',str(WORKSPACE),'rev-parse','HEAD'],text=True).strip()
    if actual!=COMMIT:raise ValueError('Unexpected upstream revision; use a separate explicitly pinned workspace')
    app=WORKSPACE/'examples/react'
    if install:
        env={**os.environ,'npm_config_cache':str(WORKSPACE/'.npm-cache'),'npm_config_update_notifier':'false'}
        subprocess.run(['npm','ci','--no-audit','--no-fund'],cwd=app,env=env,check=True)
        subprocess.run(['npm','run','build'],cwd=app,env=env,check=True)
    if not (app/'dist/index.html').is_file():raise ValueError('Run explicitly with --install to build sample')
    return app


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install',action='store_true')
    print(prepare(parser.parse_args().install))
