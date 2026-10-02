"""Bounded literal route hints; never execute JavaScript or navigate templates."""
import json
from pathlib import Path
import re

from .scan import iter_repo_files, surface_dirs

EXTENSIONS = {'.js', '.jsx', '.ts', '.tsx'}


def next_directories(base):
    return [(router, base / router if (base / router).is_dir() else base / 'src' / router)
            for router in ('app', 'pages') if (base / router).is_dir() or (base / 'src' / router).is_dir()]


def next_pages(base):
    rows, diagnostics = [], []
    for router, directory in next_directories(base):
        for path in iter_repo_files(directory):
            if path.suffix not in EXTENSIONS:
                continue
            parts = path.relative_to(directory).parts
            if router == 'app':
                if path.stem != 'page':
                    continue
                if any(p.startswith('_') for p in parts[:-1]):
                    continue
                if any(p.startswith('@') or p.startswith(('(.)', '(..)', '(...)')) for p in parts[:-1]):
                    diagnostics.append({'source': str(path.relative_to(base)), 'reason': 'parallel/intercepting route unverified'})
                    continue
                segments = [p for p in parts[:-1] if not (p.startswith('(') and p.endswith(')'))]
            else:
                if parts[0] == 'api' or path.stem.startswith('_'):
                    continue
                segments = list(parts[:-1]) + ([] if path.stem == 'index' else [path.stem])
            rows.append(('/' + '/'.join(segments), path))
    return rows, diagnostics


def _join(parent, path):
    if path.startswith('/'):
        return path
    return (parent.rstrip('/') + '/' + path).rstrip('/') or '/'


# A small lexical reader supports literal arrays/objects only. Unknown property
# expressions are skipped as values, not interpreted as route strings.
TOKEN = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`|[A-Za-z_$][\w$]*|[^\s]', re.M)


def _tokens(text):
    return [m.group() for m in TOKEN.finditer(text) if not m.group().startswith(('//', '/*'))]


def _literal(token):
    if token and token[0] in "\"'" and token[-1] == token[0]:
        return token[1:-1] if '\\' not in token else None
    return None


def _matching(tokens, start):
    pairs = {'[': ']', '{': '}', '(': ')'}
    stack = [pairs[tokens[start]]]
    for index in range(start + 1, len(tokens)):
        token = tokens[index]
        if token in pairs:
            stack.append(pairs[token])
        elif token == stack[-1]:
            stack.pop()
            if not stack:
                return index
    return len(tokens) - 1


def _objects(tokens, start, end):
    objects = []
    index = start + 1
    while index < end:
        if tokens[index] == '{':
            stop = _matching(tokens, index)
            row, key_index = {}, index + 1
            while key_index < stop:
                key = _literal(tokens[key_index]) or tokens[key_index]
                if key_index + 1 < stop and tokens[key_index + 1] == ':':
                    value_index = key_index + 2
                    if value_index >= stop:
                        if key in ('path', 'children'):
                            row[key] = None
                        break
                    value_stop = value_index
                    while value_stop < stop and tokens[value_stop] != ',':
                        if tokens[value_stop] in ('[', '{', '('):
                            value_stop = _matching(tokens, value_stop)
                        value_stop += 1
                    value = tokens[value_index:value_stop]
                    if key == 'path':
                        row['path'] = _literal(value[0]) if len(value) == 1 else None
                    if key == 'index':
                        row['index'] = value == ['true']
                    if key == 'children':
                        row['children'] = _objects(tokens, value_index, _matching(tokens, value_index)) if value and value[0] == '[' else None
                    key_index = value_stop + 1
                else:
                    key_index += 1
            objects.append(row)
            index = stop + 1
        elif tokens[index] in ('[', '('):
            index = _matching(tokens, index) + 1
        else:
            index += 1
    return objects


def _object_routes(text):
    tokens = _tokens(text)
    rows = []
    for index, token in enumerate(tokens):
        if token == '[' and index >= 2 and ((tokens[index-1] in ('=', ':') and 'route' in tokens[index-2].lower()) or
                (tokens[index-1] == '(' and tokens[index-2] in ('createBrowserRouter', 'createHashRouter'))):
            rows.extend(_objects(tokens, index, _matching(tokens, index)))
    return rows


def _walk_objects(rows, parent, hints, unresolved):
    for row in rows:
        if row.get('path', '') is None or parent is None:
            unresolved.append('dynamic route expression or unresolved parent')
            path = None
        else:
            path = _join(parent, row.get('path', ''))
            if 'path' in row or row.get('index'):
                hints.append(path)
        children = row.get('children', [])
        if children is None:
            unresolved.append('non-literal children')
        else:
            _walk_objects(children, path, hints, unresolved)


def _jsx_tags(text):
    # Comments and > inside element={<Layout/>} must not create/end Route tags.
    text = TOKEN.sub(lambda m: ' ' * len(m[0]) if m[0].startswith(('//', '/*')) else m[0], text)
    cursor = 0
    pattern = re.compile(r'<(/?)Route\b')
    while match := pattern.search(text, cursor):
        index, depth, quote = match.end(), 0, ''
        while index < len(text):
            char = text[index]
            if quote:
                if char == '\\':
                    index += 2
                    continue
                if char == quote:
                    quote = ''
            elif char in ('"', "'", '`'):
                quote = char
            elif char == '{':
                depth += 1
            elif char == '}':
                depth = max(0, depth - 1)
            elif char == '>' and depth == 0:
                yield match[1], text[match.end():index]
                break
            index += 1
        cursor = index + 1


def _jsx_routes(text):
    stack, hints, unresolved = ['/'], [], []
    for closing, attributes in _jsx_tags(text):
        if closing:
            if len(stack) > 1:
                stack.pop()
            continue
        literal = re.search(r'\bpath\s*=\s*(?:\{\s*)?(["\'])(.*?)\1', attributes)
        path = _join(stack[-1], literal[2]) if literal and stack[-1] is not None else stack[-1]
        if not literal and re.search(r'\bpath\s*=', attributes):
            path = None
            unresolved.append('non-literal JSX path')
        if path is not None and (literal or re.search(r'\bindex\b', attributes)):
            hints.append(path)
        if not attributes.rstrip().endswith('/'):
            stack.append(path)
    return hints, unresolved


def route_metadata(root: Path, framework: str, manifest=None):
    base = manifest.parent if manifest else root
    hints, diagnostics, modes = [], [], set()
    if framework == 'Next.js':
        rows, problems = next_pages(base)
        hints = [{'path': route, 'source': path.relative_to(root).as_posix(), 'router': 'next',
                  'dynamic': '[' in route, 'template': '[' in route} for route, path in rows]
        diagnostics.extend({**p, 'source': (base / p['source']).relative_to(root).as_posix()} for p in problems)
        for router, directory in next_directories(base):
            if directory == base / router and (base / 'src' / router).is_dir():
                diagnostics.append({'source': f'src/{router}', 'reason': f'ignored because root {router} exists'})
        return hints, diagnostics, 'history'
    if framework not in ('React', 'Vue', 'Nuxt'):
        return [], [], 'unknown'
    paths = {p for p in base.iterdir() if p.is_file() and not p.is_symlink() and p.suffix in EXTENSIONS}
    for relative in surface_dirs(root, framework, manifest):
        paths.update(p for p in iter_repo_files(root / relative) if p.suffix in EXTENSIONS)
    for index, path in enumerate(sorted(paths)):
        if index >= 128:
            diagnostics.append({'reason': 'route file budget 128 exhausted'})
            break
        try:
            with path.open(encoding='utf-8', errors='replace') as stream:
                text = stream.read(256001)
        except OSError as exc:
            diagnostics.append({'source': path.relative_to(root).as_posix(), 'reason': f'unreadable route source: {type(exc).__name__}'})
            continue
        if len(text) > 256000:
            diagnostics.append({'source': path.relative_to(root).as_posix(), 'reason': 'route file truncated at 256000 characters'})
            text = text[:256000]
        relative = path.relative_to(root).as_posix()
        if not any(marker in text for marker in ('<Route', 'routes', 'Routes', 'createBrowserRouter', 'createHashRouter')):
            continue
        if any(marker in text for marker in ('createWebHashHistory', 'createHashRouter', 'HashRouter')):
            modes.add('hash')
        if any(marker in text for marker in ('createWebHistory', 'createBrowserRouter', 'BrowserRouter')):
            modes.add('history')
        parsed, unresolved = _jsx_routes(text) if '<Route' in text else ([], [])
        try:
            objects = _object_routes(text)
            _walk_objects(objects, '/', parsed, unresolved)
        except (IndexError, RecursionError):
            unresolved.append('literal route parser could not resolve malformed/deep configuration')
        diagnostics.extend({'source': relative, 'reason': reason} for reason in sorted(set(unresolved)))
        hints.extend({'path': route, 'source': relative, 'router': framework.lower(),
                      'dynamic': ':' in route or '*' in route, 'template': ':' in route or '*' in route} for route in sorted(set(parsed)))
    if len(modes) > 1:
        diagnostics.append({'reason': 'multiple router modes; explicit deployment input required'})
    return hints, diagnostics, next(iter(modes)) if len(modes) == 1 else 'unknown'
