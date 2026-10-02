"""Offline deterministic Codex-protocol substitute. Never accesses an account."""
import json
import os
from pathlib import Path
import re
import sys
import time

if sys.argv[1:3] == ['login', 'status']:
    print('Logged in using ChatGPT (offline test substitute)')
    sys.exit(0)
model = sys.argv[sys.argv.index('--model') + 1]
prompt = sys.stdin.read()
with Path(__file__).with_suffix('.calls.jsonl').open('a') as output:
    output.write(json.dumps({'model': model, 'prompt': prompt}) + '\n')
if model.endswith('-block'):
    Path(__file__).with_suffix('.blocked').write_text(str(os.getpid()))
    time.sleep(120)
role = model.removesuffix('-block')
expected = 'Save should show feedback'
if role == 'gist':
    if '定位专家' in prompt:
        text = json.dumps({'selectors': [], 'keywords': [], 'summary': 'Requested scope not found'})
    elif '产品地图' in prompt:
        text = '{"areas":[],"relations":[]}'
    else:
        text = 'A save page for ordinary users'
elif role == 'expectation':
    text = json.dumps({'expectations': [{'text': expected, 'expectation_basis': {
        'type': 'interaction_convention', 'reference': 'A submission action normally gives visible feedback'}}]})
elif role == 'visual':
    text = '{"changes":[],"summary":"No visible feedback"}'
elif role == 'judge':
    identity = re.search(r'"expectation_id":\s*"(EX-[^"]+)"', prompt).group(1)
    text = json.dumps({'status': 'mismatch', 'mismatches': [{'expectation_id': identity,
        'expectation': expected, 'observation': 'No feedback appeared', 'level': 'medium',
        'reasoning': 'Save normally gives the user feedback'}]})
elif role == 'investigator':
    text = '{"root_cause_hypothesis":"Cause unverified in offline test","reproduction_steps":[],"technical_evidence":{},"affected_components":[]}'
else:
    text = '<p>Offline substitute summary</p>'
for event in [{'type': 'turn.started'}, {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': text}},
              {'type': 'turn.completed', 'usage': {'input_tokens': 10, 'output_tokens': 3}}]:
    print(json.dumps(event))
