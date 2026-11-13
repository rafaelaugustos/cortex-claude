import io
import json

import pytest

from cortex_claude.reliability.hook_input import HookInputTooLarge, read_input


@pytest.mark.parametrize('size', [63, 64])
def test_complete_document_at_or_below_byte_limit(size):
    raw = b'{"value":"' + b'x' * (size - 12) + b'"}'
    assert len(raw) == size
    assert json.loads(read_input(io.BytesIO(raw), max_bytes=64))['value'] == 'x' * (size - 12)


def test_limit_counts_utf8_bytes_not_characters():
    raw = json.dumps({'value': '🧠'}, ensure_ascii=False).encode('utf-8')
    assert json.loads(read_input(io.BytesIO(raw), max_bytes=len(raw))) == {'value': '🧠'}
    with pytest.raises(HookInputTooLarge):
        read_input(io.BytesIO(raw), max_bytes=len(raw) - 1)


def test_overflow_detection_is_bounded_even_if_the_prefix_is_valid_json():
    class BoundedStream(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 65, 'Input must not be read without a bound'
            return super().read(size)

    stream = BoundedStream(b'{}' + b' ' * 1000)
    with pytest.raises(HookInputTooLarge):
        read_input(stream, max_bytes=64)
    assert stream.tell() == 65
