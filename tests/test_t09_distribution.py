"""Distribution asset boundary and clean-environment verifier planning."""
from pathlib import Path
import tarfile
import io
import zipfile

import pytest
from scripts.verify_t09_distribution import inspect_distribution, extract_sdist, main


def archives(tmp_path, foreign=''):
    wheel=tmp_path/'alienqa-0.1.0-py3-none-any.whl'
    with zipfile.ZipFile(wheel,'w') as z:
        for name in ['alienqa/ui/templates/index.html','alienqa/review/templates/inbox.html',
                     'alienqa-0.1.0.data/data/share/alienqa/config.yaml',
                     'alienqa-0.1.0.data/data/share/alienqa/codex.yaml']:z.writestr(name,'fixture')
        if foreign:z.writestr(foreign,'foreign')
    sdist=tmp_path/'alienqa-0.1.0.tar.gz'
    with tarfile.open(sdist,'w:gz') as z:
        for name in ['pyproject.toml','requirements-dev.lock','tests/fixtures/cases/manifest.json',
                     'tests/fixtures/cases/public/index.html','tests/fixtures/t07-model-provider.py']:
            info=tarfile.TarInfo('alienqa-0.1.0/'+name);info.size=7;z.addfile(info,io.BytesIO(b'fixture'))
    return wheel,sdist


def test_distribution_has_runtime_and_versioned_test_assets(tmp_path):
    facts=inspect_distribution(*archives(tmp_path))
    assert facts['runtime_assets']=='present' and facts['acceptance_assets']=='present'
    assert facts['external_directories']=='excluded'


@pytest.mark.parametrize('foreign',['node_modules/a/index.js','artifacts/run/cookie.json','examples/open-source/app/package.json'])
def test_foreign_payload_is_rejected(tmp_path,foreign):
    with pytest.raises(ValueError):inspect_distribution(*archives(tmp_path,foreign))


def test_sdist_extraction_rejects_escape_and_links(tmp_path):
    for name in ('../escape','package/evil'):
        archive=tmp_path/'bad.tar.gz'
        with tarfile.open(archive,'w:gz') as z:
            info=tarfile.TarInfo(name)
            if name.endswith('evil'):info.type=tarfile.SYMTYPE;info.linkname='../escape'
            z.addfile(info)
        with pytest.raises(ValueError):extract_sdist(archive,tmp_path/'out')


def test_resume_cannot_use_foreign_directory(tmp_path):
    wheel,sdist=archives(tmp_path)
    with pytest.raises(SystemExit):
        main(['--wheel',str(wheel),'--sdist',str(sdist),'--resume',str(tmp_path)])
