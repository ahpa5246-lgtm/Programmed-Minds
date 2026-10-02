"""Fixed adapters for original verification tools in a trusted repository.

The configuration is supplied by the user, never by generated agent output. These
checks execute repository code; this module is a command boundary, not a sandbox.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time
from urllib.parse import unquote, urlsplit

TOOLS = frozenset({'semgrep', 'gitleaks', 'osv', 'trivy', 'zap', 'pgtap', 'playwright', 'lighthouse', 'size-limit', 'k6', 'python-tests'})
NETWORK_TOOLS = frozenset({'zap', 'k6', 'lighthouse', 'playwright'})
MAX_LOG_BYTES = 65536
_RULES = Path(__file__).resolve().parent / 'resources' / 'semgrep-python.yml'
_COMMON = {'name', 'required', 'enabled', 'reason', 'timeout', 'requirement_ids'}
_EXTRA = {'semgrep': {'config'}, 'pgtap': {'tests_dir', 'database', 'db_user', 'password_env'}, 'python-tests': {'tests_dir'}, 'playwright': {'config', 'url'}, 'lighthouse': {'config', 'url'}, 'k6': {'script', 'url'}, 'zap': {'url'}, 'size-limit': {'config'}}


def sanitize(text: str) -> str:
    """Best-effort redaction; original tools may still emit unexpected secrets."""
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?(?:-----END [^-]*PRIVATE KEY-----|\Z)', '[REDACTED PRIVATE KEY]', text)
    text = re.sub(r'(?i)(\b(?:api[_-]?key|secret|password|passwd|token|authorization|credential)\b["\x27]?\s*[:=]\s*)(?:["\x27][^"\x27\n]*["\x27]|[^\s,;]+)', r'\1[REDACTED]', text)
    text = re.sub(r'(?i)\bBearer\s+[^\s"\x27]+', 'Bearer [REDACTED]', text)
    text = re.sub(r'\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]+|AKIA[A-Z0-9]{16})\b', '[REDACTED]', text)
    text = re.sub(r'(https?://)[^/\s:@]+:[^/\s@]+@', r'\1[REDACTED]@', text)
    return ''.join(c for c in text if c in '\n\t' or ord(c) >= 32)


def _execute(argv: list[str], cwd: Path, timeout: float, extra_env: dict) -> tuple[int, float, str, bool]:
    """Drain output without unbounded memory/disk; kill descendants on deadline."""
    env = {key: value for key, value in os.environ.items() if key in {'PATH', 'HOME', 'TMPDIR', 'TEMP', 'SYSTEMROOT', 'SSL_CERT_FILE', 'SSL_CERT_DIR'}}
    env.update({'NO_COLOR': '1', 'CI': '1', **extra_env})
    started = time.monotonic()
    proc = subprocess.Popen(argv, cwd=cwd, env=env, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    head = bytearray()
    tail = bytearray()
    total = 0
    timed_out = False
    with selectors.DefaultSelector() as selector:
        selector.register(proc.stdout, selectors.EVENT_READ)
        try:
            while selector.get_map():
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    timed_out = True
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    break
                for key, _ in selector.select(min(remaining, .1)):
                    data = os.read(key.fd, 8192)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(data)
                    needed = MAX_LOG_BYTES // 2 - len(head)
                    head.extend(data[:max(0, needed)])
                    tail.extend(data[max(0, needed):])
                    del tail[:max(0, len(tail) - MAX_LOG_BYTES // 2)]
        finally:
            # Descendants that retained pipes must not survive a check timeout.
            try:
                proc.wait(timeout=max(.001, timeout - (time.monotonic() - started)))
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait(timeout=5)
            proc.stdout.close()
    marker = b'\n[LOG TRUNCATED]\n' if total > MAX_LOG_BYTES else b''
    log = sanitize((bytes(head) + marker + bytes(tail)).decode('utf-8', errors='replace'))
    # Redact any explicitly supplied secret, even if emitted without a label.
    for key, value in extra_env.items():
        if key == 'PGPASSWORD' and value:
            log = log.replace(value, '[REDACTED]')
    return proc.returncode, time.monotonic() - started, log, timed_out


def _no_symlink(path: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError('Symlink paths are not permitted')


def _relative_file(target: Path, value: str, directory: bool = False) -> Path:
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid relative path')
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Paths must remain inside target')
    result = target / path
    _no_symlink(result)
    if not result.resolve().is_relative_to(target):
        raise ValueError('Path escapes target')
    if directory and not result.is_dir():
        raise ValueError('Test directory is missing')
    if not directory and not result.is_file():
        raise ValueError('Tool configuration or script is missing')
    return result


def _url(value: str) -> str:
    if not isinstance(value, str) or not value or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Invalid target URL')
    decoded = unquote(unquote(value))
    if any(ord(c) < 32 or ord(c) == 127 for c in decoded) or '\\' in decoded:
        raise ValueError('Control characters in URL')
    parts = urlsplit(value)
    if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username is not None or parts.password is not None or parts.query or parts.fragment:
        raise ValueError('Use an HTTP(S) URL without credentials, query or fragment')
    if parts.port is not None and not 1 <= parts.port <= 65535:
        raise ValueError('Invalid port')
    return value


def _validate(config: dict) -> list[dict]:
    if not isinstance(config, dict) or set(config) - {'checks', 'owned_urls', 'allow_network'}:
        raise ValueError('Unknown checks configuration keys')
    entries = config.get('checks', [])
    if not isinstance(entries, list) or len(entries) > len(TOOLS):
        raise ValueError('checks must be a bounded list')
    if not isinstance(config.get('owned_urls', []), list) or any(not isinstance(u, str) for u in config.get('owned_urls', [])):
        raise ValueError('owned_urls must be a list of explicit URL strings')
    if type(config.get('allow_network', False)) is not bool:
        raise ValueError('allow_network must be boolean')
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get('name'), str) or entry['name'] not in TOOLS:
            raise ValueError('Unknown tool name')
        name = entry['name']
        if name in seen or set(entry) - (_COMMON | _EXTRA.get(name, set())):
            raise ValueError('Duplicate check or unknown options; arbitrary argv is prohibited')
        seen.add(name)
        requirements = entry.get('requirement_ids', [])
        if not isinstance(requirements, list) or len(requirements) > 200 or any(not isinstance(r, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', r) for r in requirements) or len(set(requirements)) != len(requirements):
            raise ValueError('requirement_ids must be distinct bounded identifiers')
        if any(type(entry.get(k, True)) is not bool for k in ('enabled', 'required')):
            raise ValueError('enabled and required must be boolean')
        if not isinstance(entry.get('reason', ''), str):
            raise ValueError('reason must be a string')
        timeout = entry.get('timeout', 120)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not .05 <= timeout <= 1800:
            raise ValueError('timeout must be between .05 and 1800 seconds')
    return entries


def _command(target: Path, entry: dict, config: dict, output: Path) -> tuple[list[str], dict]:
    name = entry['name']
    env = {}
    if name in NETWORK_TOOLS:
        url = _url(entry.get('url'))
        allowed = [_url(u) for u in config.get('owned_urls', [])]
        if config.get('allow_network') is not True or url not in allowed:
            raise ValueError('Network checks require allow_network and exact explicit owned_urls membership')
        env['BASE_URL'] = url
    if name == 'semgrep':
        rules = _relative_file(target, entry['config']) if 'config' in entry else _RULES
        if not rules.is_file():
            raise ValueError('Semgrep rules are missing')
        return ['semgrep', 'scan', '--config', str(rules), '--error', '--strict', '--metrics=off', '--disable-version-check', str(target)], env
    if name == 'gitleaks':
        return ['gitleaks', 'dir', '--redact', '--no-banner', str(target)], env
    if name == 'osv':
        return ['osv-scanner', 'scan', 'source', '--recursive', str(target)], env
    if name == 'trivy':
        return ['trivy', 'fs', '--scanners', 'vuln,misconfig,secret', '--exit-code', '1', '--severity', 'HIGH,CRITICAL', str(target)], env
    if name == 'zap':
        return ['zap-baseline.py', '-t', url, '-m', '1', '-T', '5', '-s'], env
    if name == 'python-tests':
        tests = _relative_file(target, entry.get('tests_dir', 'tests'), directory=True)
        if not any(tests.rglob('test*.py')):
            raise ValueError('No Python test files')
        return [sys.executable, '-m', 'unittest', 'discover', '-s', str(tests), '-v'], env
    if name == 'pgtap':
        tests = _relative_file(target, entry.get('tests_dir', 'tests/sql'), directory=True)
        files = sorted(p for p in tests.rglob('*') if p.suffix in {'.sql', '.pg'} and p.is_file())
        if not files or len(files) > 1000:
            raise ValueError('No pgTAP files or too many files')
        database = entry.get('database', '')
        user = entry.get('db_user', 'postgres')
        if not all(isinstance(v, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,62}', v) for v in (database, user)):
            raise ValueError('pgTAP requires an explicit local test database and valid user')
        if 'password_env' in entry:
            key = entry['password_env']
            if not isinstance(key, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or not os.environ.get(key):
                raise ValueError('Database password environment variable missing or invalid')
            env['PGPASSWORD'] = os.environ[key]
        return ['pg_prove', '--norc', '--verbose', '--host', 'localhost', '--dbname', database, '--username', user, *map(str, files)], env
    if name == 'playwright':
        settings = _relative_file(target, entry.get('config', 'playwright.config.ts'))
        return ['playwright', 'test', '--config', str(settings), '--reporter=json', '--forbid-only', '--workers=1', '--output', str(output / 'playwright-results')], env
    if name == 'lighthouse':
        settings = _relative_file(target, entry.get('config', 'lighthouserc.json'))
        # Autorun includes assertion; upload is forced to a local filesystem.
        return ['lhci', 'autorun', '--config=' + str(settings), '--collect.url=' + url, '--upload.target=filesystem', '--upload.outputDir=' + str(output / 'lighthouse-results')], env
    if name == 'size-limit':
        settings = _relative_file(target, entry.get('config', '.size-limit.json'))
        return ['size-limit', '--config', str(settings)], env
    if name == 'k6':
        script = _relative_file(target, entry.get('script', 'k6.js'))
        return ['k6', 'run', '--vus', '1', '--duration', '10s', '--env', 'BASE_URL=' + url, str(script)], env
    raise ValueError('Unknown check')


def _test_results(name: str, log: str) -> list[dict]:
    """Extract original reporters' per-test identifiers for requirement evidence."""
    results = []
    if name == 'python-tests':
        for identifier, outcome in re.findall(r'^\S+ \(([^)]+)\) \.\.\. (ok|skipped[^\n]*|expected failure|unexpected success|FAIL|ERROR)\s*$', log, re.MULTILINE):
            status = 'passed' if outcome == 'ok' else ('skipped' if outcome.startswith('skipped') else 'failed')
            results.append({'id': sanitize(identifier), 'status': status})
    elif name == 'pgtap':
        for outcome, label, directive in re.findall(r'^\s*(not ok|ok)\s+[0-9]+\s+-\s+([^\n#]+?)(?:\s+#\s*(SKIP|TODO)[^\n]*)?\s*$', log, re.MULTILINE | re.IGNORECASE):
            status = 'skipped' if directive else ('passed' if outcome.lower() == 'ok' else 'failed')
            results.append({'id': sanitize(label.strip()), 'status': status})
    elif name == 'playwright':
        try:
            data = json.loads(log)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError('Playwright JSON reporter output missing, malformed or truncated') from exc
        if not isinstance(data, dict) or not isinstance(data.get('suites'), list):
            raise ValueError('Playwright JSON reporter suites are missing')

        def visit(suites: list, path: list[str], depth: int = 0) -> None:
            if depth > 30:
                raise ValueError('Playwright suite nesting exceeds evidence limit')
            for suite in suites:
                if not isinstance(suite, dict) or not isinstance(suite.get('title'), str):
                    raise ValueError('Malformed Playwright suite')
                current = [*path, suite['title']]
                specs, children = suite.get('specs', []), suite.get('suites', [])
                if not isinstance(specs, list) or not isinstance(children, list):
                    raise ValueError('Malformed Playwright suite contents')
                for spec in specs:
                    if not isinstance(spec, dict) or not isinstance(spec.get('title'), str) or not isinstance(spec.get('tests'), list):
                        raise ValueError('Malformed Playwright spec')
                    for test in spec['tests']:
                        if not isinstance(test, dict) or not isinstance(test.get('results'), list):
                            raise ValueError('Malformed Playwright test results')
                        attempts = test['results']
                        expected = test.get('expectedStatus')
                        if expected == 'skipped' or test.get('status') == 'skipped':
                            status = 'skipped'
                        elif expected == 'passed' and test.get('status') == 'expected' and attempts and all(isinstance(r, dict) and r.get('status') == 'passed' for r in attempts):
                            status = 'passed'
                        else:
                            status = 'failed'
                        project = test.get('projectName', '')
                        if not isinstance(project, str):
                            raise ValueError('Malformed Playwright project name')
                        identifier = '::'.join([*current, spec['title'], *([project] if project else [])])
                        results.append({'id': sanitize(identifier), 'status': status})
                        if len(results) > 2000:
                            raise ValueError('Too many per-test evidence results')
                visit(children, current, depth + 1)
        visit(data['suites'], [])
    return results


def _tests_ran(name: str, log: str) -> bool:
    patterns = {'python-tests': r'Ran ([1-9][0-9]*) tests?\b', 'pgtap': r'Tests=([1-9][0-9]*)\b', 'playwright': r'\b([1-9][0-9]*) passed\b'}
    if name == 'playwright':
        return any(t['status'] == 'passed' for t in _test_results(name, log))
    if name not in patterns:
        return True
    counts = re.findall(patterns[name], log)
    if not counts:
        return False
    count = int(counts[-1])
    if name == 'python-tests':
        skips = re.findall(r'OK \(skipped=([0-9]+)\)', log)
        return count > (int(skips[-1]) if skips else 0)
    if name == 'pgtap' and re.search(r'Result:\s*NOTESTS', log):
        return False
    return True


def _write_new(path: Path, content: str) -> None:
    _no_symlink(path)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'w', encoding='utf-8') as stream:
        stream.write(content)


def run_checks(target: Path, config: dict, output: Path) -> dict:
    """Run user-selected checks, creating an immutable report in a new directory."""
    entries = _validate(config)
    target, output = Path(os.path.abspath(target)), Path(os.path.abspath(output))
    _no_symlink(target)
    _no_symlink(output)
    if not target.is_dir() or target in {Path('/'), Path.home(), Path('/workspace'), Path('/tmp'), Path('/etc'), Path('/usr'), Path('/var')}:
        raise ValueError('Choose a specific trusted project directory')
    for base, dirs, files in os.walk(target, followlinks=False):
        for item in dirs + files:
            path = Path(base) / item
            if path.is_symlink() and not path.resolve().is_relative_to(target):
                raise ValueError('Target contains a symlink escaping the repository')
    if output.is_relative_to(target):
        raise ValueError('Check reports must be outside the scanned target')
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for index, entry in enumerate(entries):
        name = entry['name']
        result = {'name': name, 'status': 'error', 'required': entry.get('required', True), 'requirement_ids': list(entry.get('requirement_ids', [])), 'argv': [], 'returncode': None, 'duration': 0.0, 'log': None, 'log_sha256': None, 'test_results': [], 'reason': ''}
        results.append(result)
        if not entry.get('enabled', True):
            result.update(status='not_applicable', reason=sanitize(entry.get('reason') or 'Disabled by configuration; no check executed'))
            continue
        try:
            argv, env = _command(target, entry, config, output)
            result['argv'] = argv
            if not shutil.which(argv[0]):
                result.update(status='missing', reason='Executable is not installed: ' + Path(argv[0]).name)
                continue
            rc, duration, log, timeout = _execute(argv, target, entry.get('timeout', 120), env)
            # _execute sanitizes its output; sanitize again for adapters/mocks.
            log = sanitize(log)
            log_name = f'{index:02d}-{name}.log'
            _write_new(output / log_name, log)
            result.update(returncode=rc, duration=round(duration, 6), log=log_name, log_sha256=hashlib.sha256(log.encode('utf-8')).hexdigest())
            result['test_results'] = _test_results(name, log)
            if timeout:
                result.update(status='error', reason='Check timed out; process group terminated')
            elif rc != 0:
                result.update(status='failed', reason='Tool returned a nonzero exit status; see sanitized log')
            elif not _tests_ran(name, log) or (name in {'python-tests', 'pgtap', 'playwright'} and not any(t['status'] == 'passed' for t in result['test_results'])):
                result.update(status='error', reason='No executed tests confirmed in tool output')
            else:
                result.update(status='passed', reason='Original tool exited successfully')
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            result.update(status='error', reason=sanitize(str(exc)))
    passed = any(r['status'] == 'passed' for r in results)
    blocked = any(r['status'] in {'failed', 'error'} or (r['required'] and r['status'] != 'passed') for r in results)
    report = {'status': 'passed' if passed and not blocked else 'blocked', 'checks': results}
    report['sha256'] = hashlib.sha256(json.dumps(report, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    _write_new(output / 'checks.json', json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    return report
