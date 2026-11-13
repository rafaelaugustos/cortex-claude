"""Bounded hook input. Never pass a truncated JSON document to the parser."""
from __future__ import annotations

from typing import BinaryIO

MAX_HOOK_INPUT_BYTES = 8 * 1024 * 1024


class HookInputTooLarge(ValueError):
    pass


def read_input(stream: BinaryIO, max_bytes: int = MAX_HOOK_INPUT_BYTES) -> bytes:
    # The extra byte distinguishes an exact-limit document from oversized input.
    raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise HookInputTooLarge('Hook input exceeds the byte limit')
    return raw
