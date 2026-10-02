"""Explicit clean wheel/sdist dependency and installed-flow verification.

Every venv, dependency/cache, browser, source extraction and result is confined
inside the gitignored project artifacts directory. Default tests never install.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import uuid
import venv
import zipfile

ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'node_modules','examples','baselines','artifacts','.venv','.git'}


def inspect_distribution(wheel,sdist):
    with zipfile.ZipFile(wheel) as z:names=z.namelist()
    with tarfile.open(sdist) as z:source=z.getnames()
    for name in names+source:
        if set(Path(name).parts)&EXCLUDED:raise ValueError('Foreign/runtime directories in distribution')
    for required in ('alienqa/ui/templates/index.html','alienqa/review/templates/inbox.html',
                     'share/alienqa/config.yaml','share/alienqa/codex.yaml'):
        if not any(n.endswith(required) for n in names):raise ValueError('Missing runtime asset: '+required)
    for required in ('pyproject.toml','requirements-dev.lock','tests/fixtures/cases/manifest.json',
                     'tests/fixtures/cases/public/index.html','tests/fixtures/t07-model-provider.py'):
        if not any(n.endswith(required) for n in source):raise ValueError('Missing acceptance asset: '+required)
    return {'runtime_assets':'present','acceptance_assets':'present','external_directories':'excluded'}


def extract_sdist(filename,destination):
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=True)
    with tarfile.open(filename) as archive:
        members=archive.getmembers()
        for member in members:
            path=(destination/member.name).resolve()
            if not path.is_relative_to(destination) or not (member.isdir() or member.isfile()):
                raise ValueError('Unsafe sdist path/link')
        archive.extractall(destination,members=members,filter='data')
    roots=list(destination.iterdir())
    if len(roots)!=1 or not (roots[0]/'pyproject.toml').is_file():raise ValueError('Expected one sdist project root')
    return roots[0]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel',required=True)
    parser.add_argument('--sdist',required=True)
    parser.add_argument('--skip-browser-install',action='store_true',help='Explicit existing project-local browser cache; recorded as reuse')
    parser.add_argument('--browser-path',help='Project-local browser cache; default is this verification directory')
    parser.add_argument('--resume',help='Resume this verifier\'s project-local incomplete directory; logs/history preserved')
    parser.add_argument('--stage-timeout',type=int,default=1200,help='Bound each dependency/build/browser/flow stage in seconds')
    args=parser.parse_args(argv)
    wheel,sdist=Path(args.wheel).resolve(),Path(args.sdist).resolve()
    facts=inspect_distribution(wheel,sdist)
    if args.stage_timeout < 1:parser.error('stage-timeout must be positive')
    output=Path(args.resume).resolve() if args.resume else ROOT/'artifacts/evaluation/t09-installation'/uuid.uuid4().hex
    if not output.is_relative_to(ROOT/'artifacts/evaluation/t09-installation'):
        parser.error('Resume directory must belong to project-local verifier')
    previous=json.loads((output/'summary.json').read_text()) if args.resume else None
    if previous and (previous.get('root')!=str(output) or previous.get('status') not in ('failed','running')):
        parser.error('Only a matching incomplete verification can resume')
    output.mkdir(parents=True,exist_ok=bool(args.resume))
    temp=output/'tmp';temp.mkdir(exist_ok=bool(args.resume))
    browser=Path(args.browser_path).resolve() if args.browser_path else output/'browsers'
    if not browser.is_relative_to(ROOT):parser.error('Browser cache must remain inside project')
    env={**os.environ,'TMPDIR':str(temp),'PIP_CACHE_DIR':str(output/'pip-cache'),
         'PIP_DISABLE_PIP_VERSION_CHECK':'1','PLAYWRIGHT_BROWSERS_PATH':str(browser),
         'HF_HOME':str(output/'hf-cache')}
    env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
    result={'schema_version':1,'status':'running','root':str(output),'assets':facts,
            'real_model_calls':0,'environments':[], 'browser_install':'reused_explicitly' if args.skip_browser_install else 'fresh_project_cache'}
    result['prior_attempts']=(previous.get('prior_attempts',[])+[{'status':previous['status'],'error':previous.get('error')}]) if previous else []
    def save(): (output/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    def run(command,cwd,name):
        with (output/name).open('a') as log:
            subprocess.run(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=args.stage_timeout)
    save()
    try:
        source=extract_sdist(sdist,output/'source')
        constraints=source/'requirements-dev.lock'
        for family in ('wheel','sdist'):
            directory=output/family
            target=directory/'venv'
            if target.exists():
                if not args.resume or 'include-system-site-packages = false' not in (target/'pyvenv.cfg').read_text():
                    raise ValueError('Existing environment is not a clean resumable venv')
            else:
                venv.EnvBuilder(with_pip=True,system_site_packages=False).create(target)
            python=directory/'venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
            work=directory/'work';work.mkdir(exist_ok=bool(args.resume))
            # Build tool versions match the tested backend; all runtime dependencies resolve anew.
            run([str(python),'-m','pip','install','-c',str(constraints),'build==1.6.1','setuptools==80.9.0'],work,f'{family}-build-deps.log')
            if family=='sdist':
                run([str(python),'-m','build','--wheel','--no-isolation','--outdir',str(directory/'dist'),str(source)],work,'sdist-build.log')
                installed=next((directory/'dist').glob('*.whl'))
            else:installed=wheel
            run([str(python),'-m','pip','install','-c',str(constraints),str(installed)],work,f'{family}-install.log')
            run([str(python),'-m','pip','check'],work,f'{family}-pip-check.log')
            if family=='wheel' and not args.skip_browser_install:
                run([str(python),'-m','playwright','install','chromium'],work,'browser-install.log')
            # Reuse the proven complete path in a fresh interpreter/dependency environment.
            run([str(python),str(ROOT/'scripts/verify_t07_installation.py'),'--wheel',str(installed),
                 '--fixtures',str(source/'tests/fixtures'),'--browser-path',str(browser),
                 '--output-root',str(directory/'flow')],work,f'{family}-flow.log')
            smoke_dir=Path((output/f'{family}-flow.log').read_text().strip().splitlines()[-1])
            flow=json.loads((smoke_dir/'summary.json').read_text())
            result['environments'].append({'kind':family,'python':str(python),'system_site_packages':False,
                'pip_check':'passed','import_path':flow['import_path'],'flow_summary':str(smoke_dir/'summary.json'),
                'installed_flow':{key:flow[key] for key in ('cli','real_worker_ui','replay','restart_review','offline_html')}})
            save()
        result['status']='passed';save();print(output);return 0
    except Exception as exc:
        result['status']='failed';result['error']=type(exc).__name__+': '+str(exc);save()
        print(f'Verification failed; inspect {output}',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
