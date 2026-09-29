#!/usr/bin/env python3
"""Isolated key-guard startup attempts; persist markers, never container log dumps."""
import json
import secrets
import subprocess
from manage import compose_args, clean_env, RESULTS

KEY_ERRORS = {
    'ai': {
        'missing': ('ai_key_too_short', 'RuntimeError: JWT_SECRET_BASE64 must encode at least 32 bytes'),
        'malformed': ('ai_key_invalid_base64', 'RuntimeError: JWT_SECRET_BASE64 must be valid base64'),
        'too_short': ('ai_key_too_short', 'RuntimeError: JWT_SECRET_BASE64 must encode at least 32 bytes'),
    },
    'be': {
        case: ('be_key_invalid', 'java.lang.IllegalArgumentException: JWT signing key must be canonical Base64 encoding of at least 32 bytes')
        for case in ('missing', 'malformed', 'too_short')
    },
}


def container_present(name):
    result = subprocess.run(
        ['docker', 'ps', '-a', '--filter', 'name=^/' + name + '$', '--format', '{{.Names}}'],
        capture_output=True, text=True, env=clean_env(), timeout=10)
    if result.returncode:
        raise RuntimeError('Cannot verify test container cleanup')
    return bool(result.stdout.strip())


def cleanup_test_container(name, timed_out):
    """Only the uniquely named --rm container may be stopped; no volumes are removed."""
    result = {'test_container': name, 'stop_requested': False}
    try:
        if timed_out and container_present(name):
            result['stop_requested'] = True
            stop = subprocess.run(['docker', 'stop', '--time', '5', name],
                                  capture_output=True, text=True, env=clean_env(), timeout=15)
            result['stop_exit_code'] = stop.returncode
        result['container_removed'] = not container_present(name)
        result['status'] = 'PASS' if result['container_removed'] else 'BLOCKED'
    except (subprocess.TimeoutExpired, OSError, RuntimeError) as error:
        result['status'] = 'BLOCKED'
        result['error_type'] = type(error).__name__
    return result


def main():
    rows = []
    for service, variable in [('ai', 'JWT_SECRET_BASE64'), ('be', 'JWT_SECRET')]:
        for case, value in [('missing', ''), ('malformed', 'deliberately-not-base64'), ('too_short', 'c2hvcnQ=')]:
            name = 'dodream-phase2a-keycheck-' + service + '-' + secrets.token_hex(4)
            args = compose_args('run', '--rm', '--no-deps', '--name', name, '-e', variable + '=' + value, service)
            if service == 'ai':
                args += ['python', '-c', 'import app.main']
            marker, expected = KEY_ERRORS[service][case]
            timed_out = False
            try:
                run = subprocess.run(args, capture_output=True, text=True, env=clean_env(), timeout=75)
                # Include the exact exception class/message; a generic JWT substring is insufficient.
                matched = expected in (run.stdout + run.stderr)
                row = {'name': service + '_startup_' + case + '_key',
                       'status': 'PASS' if run.returncode != 0 and matched else 'FAIL',
                       'exit_code': run.returncode, 'expected_error_marker': marker,
                       'key_error_identified': matched}
            except subprocess.TimeoutExpired:
                timed_out = True
                row = {'name': service + '_startup_' + case + '_key', 'status': 'BLOCKED',
                       'detail': 'Startup did not fail within 75 seconds', 'expected_error_marker': marker}
            except OSError as error:
                row = {'name': service + '_startup_' + case + '_key', 'status': 'BLOCKED',
                       'detail': type(error).__name__, 'expected_error_marker': marker}
            row['cleanup'] = cleanup_test_container(name, timed_out)
            if row['cleanup']['status'] != 'PASS':
                row['status'] = 'BLOCKED'
            rows.append(row)
            print(json.dumps(row))
    (RESULTS / 'startup-key-checks.json').write_text(json.dumps(rows, indent=2) + '\n')
    return int(any(row['status'] != 'PASS' for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
