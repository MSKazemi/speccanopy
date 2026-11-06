"""Mermaid labels in exported .mmd files must survive quotes and newlines.

Mermaid does not support backslash escapes inside a quoted label; a `"` ends the
label. Its documented escape is the entity code `#quot;`.
"""

from __future__ import annotations

from speccanopy.exporters import _escape_mermaid_label


def test_quotes_use_mermaid_entity_not_backslash():
    out = _escape_mermaid_label('Say "hi"\nnow')
    assert '"' not in out and '\\"' not in out
    assert out == "Say #quot;hi#quot; now"


def test_backslash_is_left_literal():
    assert _escape_mermaid_label("C:\\path") == "C:\\path"
