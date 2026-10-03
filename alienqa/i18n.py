"""Small, dependency-free bilingual catalog with request-local language selection."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from importlib import import_module
import re
from string import Formatter
from urllib.parse import urlencode, urlsplit

_language = ContextVar('alienqa_language', default='zh')
SUPPORTED_LANGUAGES = ('zh', 'en')


def normalize_language(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('Unsupported language; choose zh or en')
    language = value.strip().lower().replace('_', '-').split('-')[0]
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError('Unsupported language; choose zh or en')
    return language


def get_language() -> str:
    return _language.get()


@contextmanager
def language_context(language: str):
    token = _language.set(normalize_language(language))
    try:
        yield
    finally:
        _language.reset(token)


@lru_cache(maxsize=1)
def _messages() -> dict[str, str]:
    catalog = {}
    for area in ('core', 'ui', 'report', 'cli', 'runtime', 'infra'):
        name = f'alienqa.locales.{area}'
        try:
            module = import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name != name:
                raise
            continue
        catalog.update(module.MESSAGES)
    return catalog


def t(message: str, language: str | None = None, **values) -> str:
    selected = normalize_language(language) if language is not None else get_language()
    text = _messages().get(message, message) if selected == 'en' else message
    return text.format(**values) if values else text


def translate_text(message: str, language: str | None = None) -> str:
    """Translate known application errors, leaving embedded source values intact.

    This is for legacy exception boundaries. New messages should call t() with
    named arguments; arbitrary evidence, page text and user notes never enter it.
    """
    selected = normalize_language(language) if language is not None else get_language()
    if selected != 'en' or not isinstance(message, str):
        return message
    catalog = _messages()
    if message in catalog:
        return catalog[message]
    for source, target in catalog.items():
        if '{' not in source:
            continue
        pattern, fields = [], []
        try:
            for literal, field, spec, conversion in Formatter().parse(source):
                pattern.append(re.escape(literal))
                if field is not None:
                    fields.append(field)
                    pattern.append('(.*?)')
            if not fields:
                continue
            match = re.fullmatch(''.join(pattern), message, flags=re.DOTALL)
            if match:
                return target.format(**dict(zip(fields, match.groups())))
        except (ValueError, KeyError, IndexError):
            continue
    return message


def install_flask_i18n(app, default_language='zh', *, prefer_default=False):
    """Select a locale per request and provide safe, persistent switch links."""
    from flask import g, jsonify, redirect, request

    default = normalize_language(default_language)

    def valid_language(value):
        try:
            return normalize_language(value)
        except ValueError:
            return None

    @app.before_request
    def select_language():
        explicit = request.args.get('lang')
        if explicit is not None and valid_language(explicit) is None:
            return jsonify(error='Unsupported language; choose zh or en'), 400
        preferred = None
        # Iterate in the header's quality order, also matching regional tags.
        for candidate, quality in request.accept_languages:
            if quality > 0 and valid_language(candidate):
                preferred = valid_language(candidate)
                break
        selected = (valid_language(explicit) if explicit else None) or valid_language(
            request.cookies.get('alienqa_language')) or (default if prefer_default else preferred) or default
        g.alienqa_language_token = _language.set(selected)
        if explicit:
            g.alienqa_language_cookie = selected

    @app.teardown_request
    def restore_language(error=None):
        token = g.pop('alienqa_language_token', None)
        if token is not None:
            _language.reset(token)

    @app.after_request
    def localize_response(response):
        if response.is_json:
            data = response.get_json(silent=True)
            if isinstance(data, dict):
                changed = False
                for key in ('error', 'message'):
                    if isinstance(data.get(key), str):
                        translated = translate_text(data[key])
                        changed |= translated != data[key]
                        data[key] = translated
                if changed:
                    response.set_data(app.json.dumps(data))
        response.headers['Content-Language'] = get_language()
        response.vary.add('Cookie')
        response.vary.add('Accept-Language')
        selected = g.get('alienqa_language_cookie')
        if selected:
            response.set_cookie('alienqa_language', selected, max_age=31536000,
                                httponly=True, samesite='Lax')
        return response

    def language_url(language):
        selected = normalize_language(language)
        query = [(key, value) for key, value in request.args.items(multi=True) if key != 'lang']
        destination = request.path + ('?' + urlencode(query) if query else '')
        return '/language/' + selected + '?' + urlencode({'next': destination})

    @app.context_processor
    def language_helpers():
        return {'_': t, 'language': get_language(), 'language_url': language_url,
                'translate_text': translate_text}

    @app.get('/language/<language>')
    def switch_language(language):
        selected = valid_language(language)
        if selected is None:
            return jsonify(error='Unsupported language; choose zh or en'), 400
        destination = request.args.get('next', '/')
        try:
            parsed = urlsplit(destination)
        except ValueError:
            destination = '/'
            parsed = urlsplit(destination)
        if (parsed.scheme or parsed.netloc or not destination.startswith('/')
                or destination.startswith('//') or '\\' in destination
                or any(ord(char) < 32 for char in destination)):
            destination = '/'
        # A query locale must not override the newly selected cookie.
        from urllib.parse import parse_qsl, urlunsplit
        parsed = urlsplit(destination)
        query = urlencode([(key, value) for key, value in parse_qsl(parsed.query) if key != 'lang'])
        destination = urlunsplit(('', '', parsed.path, query, parsed.fragment))
        g.alienqa_language_cookie = selected
        _language.set(selected)
        return redirect(destination)
