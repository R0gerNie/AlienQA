"""Evaluator-side acceptance assets; labels and review answers stay outside models."""
from collections import Counter
import json
import math
from pathlib import Path
from urllib.parse import urlsplit


def load_manifest(filename):
    path = Path(filename)
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('cases'), list) or not data['cases']:
        raise ValueError('Invalid acceptance manifest schema')
    ids = set()
    for case in data['cases']:
        if not isinstance(case, dict):
            raise ValueError('Acceptance case must be an object')
        ident, entry = case.get('id'), case.get('entry')
        if not isinstance(ident, str) or not ident or ident in ids or Path(ident).name != ident:
            raise ValueError('Duplicate/invalid acceptance case id')
        ids.add(ident)
        if not isinstance(entry, str):
            raise ValueError(f'{ident}: missing entry')
        parsed = urlsplit(entry)
        if parsed.scheme or parsed.netloc or entry.startswith('/') or '..' in Path(parsed.path).parts or '\\' in entry:
            raise ValueError(f'{ident}: entry must stay in public fixture directory')
        if not case.get('reset') or not isinstance(case.get('assertions'), list) or not case['assertions'] or not isinstance(case.get('labels'), dict):
            raise ValueError(f'{ident}: missing reset/assertions/evaluator labels')
        if case.get('variant_kind') not in ('normal', 'abnormal', 'reasonable_exception'):
            raise ValueError(f'{ident}: invalid variant kind')
        if type(case.get('max_actions')) is not int or case['max_actions'] < 1 or not isinstance(case.get('actions'), list):
            raise ValueError(f'{ident}: invalid action budget/actions')
        sentinel = case['labels'].get('sentinel')
        if not isinstance(sentinel, str) or not sentinel or sentinel in case.get('unit', ''):
            raise ValueError(f'{ident}: evaluator label leaked into task')
    public = data.get('public_directory', 'public')
    if not isinstance(public, str) or Path(public).is_absolute() or '..' in Path(public).parts:
        raise ValueError('public_directory must stay beside manifest')
    return data


def product_input(case, base):
    """The only fixture inputs allowed at the pipeline/model boundary."""
    return {'url': base.rstrip('/') + '/' + case['entry'], 'unit': case.get('unit', ''),
            'max_actions': case['max_actions']}


def review_template(rows, cases):
    index = {c.get('case_id',c['id']): c for c in cases}
    return {'schema_version': 1, 'policy': 'Independent manual review; no automatic confirmation',
            'runs': [{'id': row['id'], 'case_id': row.get('case_id'),
                      'run_id': row.get('run_id'), 'checkpoint_seq': row.get('checkpoint_seq'),
                      'status': row['status'], 'reference': index.get(row.get('case_id'), {}).get('labels', {}),
                      'review_status': 'pending', 'reviewer': '', 'independent': False, 'review_minutes': None,
                      'expectation_reasonable': None, 'merge_correct': None, 'judgment_matches_visible': None,
                      'disposition': None, 'found_expected': None, 'complaint_is_false': None,
                      'false_complaint_count': None, 'notes': ''} for row in rows]}


def assess(rows, cases, review):
    index = {c['id']: c for c in cases}
    entries = review.get('runs', [])
    lookup = {entry['id']: entry for entry in entries}
    if len(lookup) != len(entries) or set(lookup) != {row['id'] for row in rows}:
        raise ValueError('Review identities do not match evaluation runs')
    reviewed, expected, found, unexplored, minutes, false_count, controls = [], 0, 0, 0, 0, 0, 0
    for row in rows:
        entry = lookup[row['id']]
        for field in ('case_id', 'run_id', 'checkpoint_seq'):
            if entry.get(field) != row.get(field):
                raise ValueError('Review belongs to a different run/checkpoint')
        case = index.get(row.get('case_id'), {})
        problem = case.get('labels', {}).get('known_problem') is True
        expected += problem
        unexplored += problem and (row['status'] == 'not_started' or not row.get('steps'))
        if entry.get('review_status') != 'reviewed':
            continue
        if (row['status'] == 'not_started' or not entry.get('reviewer') or
                type(entry.get('independent')) is not bool or type(entry.get('review_minutes')) not in (int, float) or
                not math.isfinite(entry['review_minutes']) or entry['review_minutes'] < 0 or any(type(entry.get(key)) is not bool for key in
                ('expectation_reasonable', 'merge_correct', 'judgment_matches_visible', 'found_expected', 'complaint_is_false'))):
            raise ValueError('Incomplete human assessment; keep pending rather than inventing review')
        reviewed.append(entry)
        minutes += entry['review_minutes']
        found += problem and entry['found_expected']
        if case and not problem:
            controls += 1
            count = entry.get('false_complaint_count')
            if count is None:
                count = int(entry['complaint_is_false'])
            if type(count) is not int or count < 0:
                raise ValueError('false_complaint_count must be a nonnegative integer')
            false_count += count
    dispositions = Counter(e.get('disposition') for e in reviewed)
    independent = bool(rows) and len(reviewed) == len(rows) and all(e['independent'] for e in reviewed)
    return {'planned_runs': len(rows), 'reviewed_runs': len(reviewed), 'pending_runs': len(rows)-len(reviewed),
            'discovery': {'numerator': found, 'denominator': expected, 'unexplored': unexplored},
            'false_complaints': {'numerator': false_count, 'denominator': controls},
            'reasonable_design_runs': dispositions['reasonable_design'], 'dispositions': dict(dispositions),
            'review_minutes': minutes, 'independent_review_complete': independent,
            'release_effect_gate': False, 'notice': 'Counts are a small-sample baseline, not accuracy. Real app/usefulness/threshold approval remains separate.'}


def evidence_matrix(records):
    levels = {name: 'not_run' for name in ('structure', 'browser_mechanism', 'installation', 'real_model', 'independent_review', 'user_trial')}
    platforms = {name: 'not_run' for name in ('macOS', 'Ubuntu', 'Windows')}
    for row in records:
        if row.get('level') not in levels or row.get('status') not in ('passed', 'failed', 'blocked', 'not_run') or not row.get('result'):
            raise ValueError('Evidence needs level/status/result provenance')
        if row['level'] == 'real_model' and row.get('models') == 'substitute':
            raise ValueError('Substitute model cannot certify real_model')
        current = levels[row['level']]
        priority={'not_run':0,'passed':1,'blocked':2,'failed':3}
        levels[row['level']] = max((current,row['status']),key=priority.get)
        if row.get('platform') in platforms:
            platforms[row['platform']] = row['status']
    return {'schema_version': 1, 'records': records, 'levels': levels, 'platforms': platforms,
            'release_ready': all(levels[k] == 'passed' for k in levels),
            'notice': 'Evidence levels and exact combinations are separate; a local pass does not verify other platforms.'}


def serve_cases(directory):
    from functools import partial
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from urllib.parse import parse_qs
    from .static_server import StaticHandler
    class Handler(StaticHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == '/api/result':
                raw = parse_qs(parsed.query).get('status', ['200'])[0]
                code = int(raw) if raw in ('200', '401', '422', '500') else 400
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"result":"controlled"}')
                return
            super().do_GET()
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(directory)))
    Thread(target=server.serve_forever, daemon=True).start()
    return server, f'http://127.0.0.1:{server.server_port}'
