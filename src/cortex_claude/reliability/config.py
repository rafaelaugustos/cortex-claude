from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RecoveryConfig:
    auto_backup: bool = True
    backup_interval_hours: int = 6
    backup_keep: int = 16
    auto_checkpoints: bool = True
    mirror_directory: str = ''
    web_port: int = 37800

    @classmethod
    def load(cls, home: Path):
        path = home / 'config.json'
        raw = json.loads(path.read_text()).get('reliability', {}) if path.exists() else {}
        if not isinstance(raw, dict):
            raise ValueError('reliability must be an object')
        config = cls()
        for key in ('auto_backup', 'auto_checkpoints'):
            if key in raw:
                if type(raw[key]) is not bool:
                    raise ValueError(f'reliability.{key} must be a boolean')
                setattr(config, key, raw[key])
        for key, low, high in [('backup_interval_hours', 1, 168), ('backup_keep', 2, 100), ('web_port', 1024, 65535)]:
            if key in raw:
                if type(raw[key]) is not int or not low <= raw[key] <= high:
                    raise ValueError(f'Invalid reliability.{key}')
                setattr(config, key, raw[key])
        mirror = raw.get('mirror_directory', '')
        if not isinstance(mirror, str) or (mirror and not Path(mirror).expanduser().is_absolute()):
            raise ValueError('mirror_directory must be an absolute local path')
        config.mirror_directory = mirror
        return config
