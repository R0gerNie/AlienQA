"""Record scoped test/installation provenance and an experimental release gate.

No models are called; unreadable or failed evidence never becomes a green cell.
"""
import argparse
import json
from pathlib import Path
import platform
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from alienqa.acceptance import assess, evidence_matrix, load_manifest
from alienqa.persistence import atomic_write_json


def test_record(filename,level,platform_name='macOS'):
    root=ET.parse(filename).getroot()
    tests=list(root.iter('testcase'))
    failed=sum(t.find('failure') is not None or t.find('error') is not None for t in tests)
    skipped=sum(t.find('skipped') is not None for t in tests)
    return {'id':Path(filename).stem,'level':level,'status':'failed' if failed else 'blocked' if skipped or not tests else 'passed',
            'platform':platform_name,'python':platform.python_version(),'models':'substitute',
            'tests':len(tests),'failures':failed,'skipped':skipped,'result':str(filename)}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--junit',action='append',default=[])
    parser.add_argument('--structural-junit',action='append',default=[])
    parser.add_argument('--framework-junit',action='append',default=[])
    parser.add_argument('--installation',action='append',default=[])
    parser.add_argument('--evaluation')
    parser.add_argument('--review')
    parser.add_argument('--manifest',default=str(ROOT/'tests/fixtures/cases/manifest.json'))
    parser.add_argument('--output',required=True)
    args=parser.parse_args(argv)
    system={'Darwin':'macOS','Linux':'Ubuntu','Windows':'Windows'}.get(platform.system(),platform.system())
    records=[test_record(p,'browser_mechanism',system) for p in args.junit+args.framework_junit]
    records += [test_record(p,'structure',system) for p in args.structural_junit]
    for filename in args.installation:
        data=json.loads(Path(filename).read_text())
        environments=data.get('environments',[])
        if data.get('status')=='passed' and (len(environments)!=2 or {e.get('kind') for e in environments}!={'wheel','sdist'} or
                any(e.get('system_site_packages') is not False or e.get('pip_check')!='passed' for e in environments)):
            raise ValueError('Both clean wheel and sdist environments are required')
        records.append({'id':'distribution','level':'installation','platform':system,'python':platform.python_version(),
                        'status':'passed' if data.get('status')=='passed' else 'failed','models':'substitute','result':filename})
    extra={}
    if args.evaluation:
        evaluation=json.loads(Path(args.evaluation).read_text())
        # Raw accounting provenance is explicit; synthetic responses stay synthetic.
        extra['evaluation']=evaluation.get('summary',{})
        runs=evaluation.get('runs',[])
        if evaluation.get('inference_kind')=='real' and evaluation.get('invocations_used',0)>0 and runs:
            statuses={r.get('status') for r in runs}
            records.append({'id':'model-execution','level':'real_model','models':'real','platform':system,
                'status':'failed' if 'error' in statuses else 'passed' if statuses=={'completed'} else 'blocked',
                'result':args.evaluation,'scope':'Execution/accounting baseline; not quality/usefulness certification'})
        if args.review:
            review=json.loads(Path(args.review).read_text())
            extra['assessment']=assess(evaluation['runs'],load_manifest(args.manifest)['cases'],review)
            records.append({'id':'human-review','level':'independent_review','models':'human','platform':system,
                'status':'passed' if extra['assessment']['independent_review_complete'] else 'blocked','result':args.review})
    result={**evidence_matrix(records),**extra}
    result['release_status']='experimental; engineering execution and supported combinations gate release; human feedback is optional'
    atomic_write_json(args.output,result)
    print(args.output)
    return 1 if any(r['status']=='failed' and r['level'] in result['required_levels'] for r in records) else 0


if __name__=='__main__':raise SystemExit(main())
