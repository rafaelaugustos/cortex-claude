from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main(args: list[str]) -> None:
    parser = argparse.ArgumentParser(description='Inspect recovery, verified backups and local services')
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('status')
    commands.add_parser('backup')
    commands.add_parser('list')
    commands.add_parser('retry')
    commands.add_parser('self-test')
    commands.add_parser('diagnose')
    commands.add_parser('install-services')
    client = commands.add_parser('install-codex')
    client.add_argument('--directory', type=Path, default=Path.home() / '.codex')
    verify = commands.add_parser('verify')
    verify.add_argument('backup_id')
    restore_parser = commands.add_parser('restore')
    restore_parser.add_argument('backup_id')
    restore_parser.add_argument('--destination', required=True, type=Path)
    options = parser.parse_args(args)
    home = Path(os.environ.get('CORTEX_HOME', '~/.cortex-claude')).expanduser()
    try:
        from cortex_claude.reliability import backups
        if options.action == 'status':
            from cortex_claude.reliability.health import report
            result = report(home)
        elif options.action == 'self-test':
            from cortex_claude.reliability.probe import run
            result = run(home)
        elif options.action == 'diagnose':
            from cortex_claude.reliability.diagnostics import sample
            result = sample(home)
        elif options.action == 'backup':
            result = backups.create(home)
            result['restore_check'] = backups.test_restore(home, result['id'])
        elif options.action == 'list':
            result = {'items': backups.snapshots(home)}
        elif options.action == 'verify':
            result = backups.test_restore(home, options.backup_id)
        elif options.action == 'restore':
            result = backups.restore(home, options.backup_id, options.destination.expanduser())
        elif options.action == 'retry':
            from cortex_claude.reliability.queue import retry
            result = retry(home)
        elif options.action == 'install-services':
            from cortex_claude.reliability.services import install
            result = install(home)
        else:
            from cortex_claude.reliability.clients import install_codex
            result = install_codex(home, options.directory)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if options.action == 'self-test' and result['status'] != 'passed':
            raise SystemExit(1)
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error), 'type': type(error).__name__}, ensure_ascii=False))
        raise SystemExit(1)
