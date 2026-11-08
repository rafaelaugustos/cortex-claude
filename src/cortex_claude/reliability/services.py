from __future__ import annotations

import json
import os
import plistlib
import signal
import subprocess
import sys
import time
from pathlib import Path

from cortex_claude.reliability.config import RecoveryConfig
from cortex_claude.reliability.files import atomic_write, state

LABELS = {'daemon': 'com.cortexclaude.daemon', 'web': 'com.cortexclaude.web'}


def prepare(home: Path, directory: Path, python: str | None = None) -> list[Path]:
    config = RecoveryConfig.load(home)
    result = []
    home.mkdir(parents=True, exist_ok=True)
    for service, label in LABELS.items():
        path = directory / (label + '.plist')
        value = {'Label': label, 'ProgramArguments': [python or sys.executable, '-m', 'cortex_claude', service] + ([str(config.web_port)] if service == 'web' else []),
                 'WorkingDirectory': str(home), 'EnvironmentVariables': {'CORTEX_HOME': str(home), 'PYTHONUNBUFFERED': '1'},
                 'RunAtLoad': True, 'KeepAlive': True, 'ThrottleInterval': 10, 'ExitTimeOut': 30,
                 'StandardOutPath': str(home / (service + '.log')), 'StandardErrorPath': str(home / (service + '.log')),
                 'ProcessType': 'Background'}
        atomic_write(path, plistlib.dumps(value))
        result.append(path)
    return result


def stop_recorded(home: Path, service: str) -> bool:
    pid_path = home / ('cortex.pid' if service == 'daemon' else 'web.pid')
    if not pid_path.exists():
        return False
    pid = int(pid_path.read_text().strip())
    if pid <= 1:
        raise ValueError('Invalid Cortex process identifier')
    process = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True, timeout=3)
    if not process.stdout.strip():
        return False
    if f' -m cortex_claude {service}' not in process.stdout:
        raise ValueError('Recorded process is not the expected Cortex service; left untouched')
    os.kill(pid, signal.SIGTERM)
    for _ in range(150):
        if subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, timeout=3).returncode:
            return True
        time.sleep(.1)
    raise TimeoutError('Cortex service did not stop cleanly; no force kill performed')


def install(home: Path) -> dict:
    if sys.platform != 'darwin':
        raise ValueError('Automatic login services currently support macOS; use the documented service commands on other platforms')
    domain = f'gui/{os.getuid()}'
    directory = Path.home() / 'Library' / 'LaunchAgents'
    paths = prepare(home, directory)
    for service, label in LABELS.items():
        target = domain + '/' + label
        exists = subprocess.run(['launchctl', 'print', target], capture_output=True, timeout=5).returncode == 0
        if exists:
            subprocess.run(['launchctl', 'bootout', target], check=True, capture_output=True, timeout=30)
        stop_recorded(home, service)
        path = next(path for path in paths if path.stem == label)
        # launchd can acknowledge bootout before releasing the registration.
        # A bounded retry handles that transient EIO without changing trust or
        # killing unrelated processes. All other failures remain visible.
        for attempt in range(6):
            result = subprocess.run(['launchctl', 'bootstrap', domain, str(path)], capture_output=True, timeout=15)
            if result.returncode == 0:
                break
            if result.returncode != 5 or attempt == 5:
                result.check_returncode()
            time.sleep(.5)
    state(home, services_installed_at=time.time(), service_manager='launchd')
    return {'installed': True, 'manager': 'launchd', 'starts': 'at user login', 'services': list(LABELS.values())}


def status() -> dict:
    result = {}
    for service, label in LABELS.items():
        path = Path.home() / 'Library' / 'LaunchAgents' / (label + '.plist')
        result[service] = {'installed': path.exists(), 'label': label}
    return result
