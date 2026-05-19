from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any


EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".java": "java",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
}


@dataclass
class Symbol:
    name: str
    kind: str
    line: int
    language: str
    path: str
    calls: list[str] = field(default_factory=list)
    extends: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


# Tree-sitter S-expression queries per language. We capture functions, classes/structs,
# imports, and call expressions. Each query uses @name / @body / @callee captures
# that the extractor interprets uniformly.
QUERIES: dict[str, str] = {
    "python": """
        (function_definition name: (identifier) @func.name) @func.body
        (class_definition name: (identifier) @class.name (argument_list (identifier) @class.extends)?) @class.body
        (class_definition name: (identifier) @class.name) @class.body
        (import_statement name: (dotted_name) @import.name)
        (import_from_statement module_name: (dotted_name) @import.name)
        (call function: (identifier) @call.name)
        (call function: (attribute attribute: (identifier) @call.name))
    """,
    "javascript": """
        (function_declaration name: (identifier) @func.name) @func.body
        (method_definition name: (property_identifier) @func.name) @func.body
        (class_declaration name: (identifier) @class.name) @class.body
        (variable_declarator name: (identifier) @func.name value: [(arrow_function) (function_expression)]) @func.body
        (import_statement source: (string (string_fragment) @import.name))
        (call_expression function: (identifier) @call.name)
        (call_expression function: (member_expression property: (property_identifier) @call.name))
    """,
    "typescript": """
        (function_declaration name: (identifier) @func.name) @func.body
        (method_definition name: (property_identifier) @func.name) @func.body
        (class_declaration name: (type_identifier) @class.name) @class.body
        (interface_declaration name: (type_identifier) @class.name) @class.body
        (variable_declarator name: (identifier) @func.name value: [(arrow_function) (function_expression)]) @func.body
        (import_statement source: (string (string_fragment) @import.name))
        (call_expression function: (identifier) @call.name)
        (call_expression function: (member_expression property: (property_identifier) @call.name))
    """,
    "tsx": """
        (function_declaration name: (identifier) @func.name) @func.body
        (method_definition name: (property_identifier) @func.name) @func.body
        (class_declaration name: (type_identifier) @class.name) @class.body
        (interface_declaration name: (type_identifier) @class.name) @class.body
        (variable_declarator name: (identifier) @func.name value: [(arrow_function) (function_expression)]) @func.body
        (import_statement source: (string (string_fragment) @import.name))
        (call_expression function: (identifier) @call.name)
        (call_expression function: (member_expression property: (property_identifier) @call.name))
    """,
    "go": """
        (function_declaration name: (identifier) @func.name) @func.body
        (method_declaration name: (field_identifier) @func.name) @func.body
        (type_declaration (type_spec name: (type_identifier) @class.name)) @class.body
        (import_spec path: (interpreted_string_literal) @import.name)
        (call_expression function: (identifier) @call.name)
        (call_expression function: (selector_expression field: (field_identifier) @call.name))
    """,
    "java": """
        (method_declaration name: (identifier) @func.name) @func.body
        (constructor_declaration name: (identifier) @func.name) @func.body
        (class_declaration name: (identifier) @class.name) @class.body
        (interface_declaration name: (identifier) @class.name) @class.body
        (import_declaration (scoped_identifier) @import.name)
        (method_invocation name: (identifier) @call.name)
    """,
    "swift": """
        (function_declaration name: (simple_identifier) @func.name) @func.body
        (class_declaration name: (type_identifier) @class.name) @class.body
        (protocol_declaration name: (type_identifier) @class.name) @class.body
        (import_declaration (identifier) @import.name)
        (call_expression (simple_identifier) @call.name)
    """,
    "kotlin": """
        (function_declaration (identifier) @func.name) @func.body
        (class_declaration (identifier) @class.name) @class.body
        (import (qualified_identifier) @import.name)
        (call_expression (identifier) @call.name)
    """,
}


def is_supported_path(path: str | Path) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in EXTENSION_TO_LANGUAGE


def _detect_language(path: str | Path) -> str | None:
    suffix = Path(path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(suffix)


@lru_cache(maxsize=16)
def _get_parser(language: str) -> tuple[Any, Any] | None:
    """Load a tree-sitter parser for the language. Returns (parser, language_obj)
    or None if the grammar is not installed."""
    try:
        from tree_sitter import Language, Parser
    except ImportError:
        return None

    try:
        if language == "python":
            import tree_sitter_python as ts_mod
            lang_capsule = ts_mod.language()
        elif language == "javascript":
            import tree_sitter_javascript as ts_mod
            lang_capsule = ts_mod.language()
        elif language == "typescript":
            import tree_sitter_typescript as ts_mod
            lang_capsule = ts_mod.language_typescript()
        elif language == "tsx":
            import tree_sitter_typescript as ts_mod
            lang_capsule = ts_mod.language_tsx()
        elif language == "go":
            import tree_sitter_go as ts_mod
            lang_capsule = ts_mod.language()
        elif language == "java":
            import tree_sitter_java as ts_mod
            lang_capsule = ts_mod.language()
        elif language == "swift":
            import tree_sitter_swift as ts_mod
            lang_capsule = ts_mod.language()
        elif language == "kotlin":
            import tree_sitter_kotlin as ts_mod
            lang_capsule = ts_mod.language()
        else:
            return None
    except ImportError:
        return None

    lang_obj = Language(lang_capsule)
    return Parser(lang_obj), lang_obj


def extract_symbols(path: str | Path, content: str) -> list[Symbol]:
    """Parse source content and return top-level symbols with their calls/imports.

    Returns [] if:
      - The file extension isn't supported.
      - The grammar package isn't installed (graceful degrade).
      - Parsing fails.
    """
    language = _detect_language(path)
    if language is None:
        return []

    loaded = _get_parser(language)
    if loaded is None:
        return []
    parser, lang_obj = loaded

    try:
        tree = parser.parse(content.encode("utf-8"))
    except Exception:
        return []

    query_source = QUERIES.get(language)
    if not query_source:
        return []

    try:
        from tree_sitter import Query, QueryCursor
        query = Query(lang_obj, query_source)
        cursor = QueryCursor(query)
    except ImportError:
        try:
            query = lang_obj.query(query_source)
        except Exception:
            return []
        cursor = None
    except Exception:
        return []

    if cursor is not None:
        captures = cursor.captures(tree.root_node)
    else:
        captures = query.captures(tree.root_node)

    symbols_by_body: dict[tuple[int, int], Symbol] = {}
    pending_calls: list[tuple[int, str]] = []
    pending_imports: list[str] = []
    pending_extends: list[str] = []

    path_str = str(path)
    captures_iter = (
        [(node, name) for name, nodes in captures.items() for node in nodes]
        if isinstance(captures, dict)
        else list(captures)
    )

    bodies: list[tuple[tuple[int, int], str, int, str]] = []
    pending_extends_with_pos: list[tuple[int, str]] = []

    for node, capture_name in captures_iter:
        if capture_name == "func.name" or capture_name == "class.name":
            kind = "function" if capture_name == "func.name" else "class"
            text = node.text.decode("utf-8", errors="ignore")
            parent = node.parent
            while parent is not None and parent.type not in {
                "function_definition", "function_declaration", "method_definition", "method_declaration",
                "class_definition", "class_declaration", "constructor_declaration",
                "interface_declaration", "protocol_declaration", "variable_declarator",
                "type_declaration", "type_spec",
            }:
                parent = parent.parent
            if parent is None:
                continue
            key = (parent.start_byte, parent.end_byte)
            bodies.append((key, kind, node.start_point[0] + 1, text))
        elif capture_name == "call.name":
            text = node.text.decode("utf-8", errors="ignore")
            pending_calls.append((node.start_byte, text))
        elif capture_name == "import.name":
            text = node.text.decode("utf-8", errors="ignore").strip("\"'")
            pending_imports.append(text)
        elif capture_name == "class.extends":
            text = node.text.decode("utf-8", errors="ignore")
            pending_extends_with_pos.append((node.start_byte, text))

    # Pick the innermost (smallest) body containing the name. Multiple captures may
    # overlap (e.g. class + method); we want the most specific match.
    seen_bodies: dict[tuple[int, int], Symbol] = {}
    for key, kind, line, name in bodies:
        if key in seen_bodies:
            continue
        seen_bodies[key] = Symbol(
            name=name,
            kind=kind,
            line=line,
            language=language,
            path=path_str,
        )
    symbols_by_body = seen_bodies

    # Sort body ranges by size (smallest first) so call/extend assignment picks
    # the innermost enclosing symbol.
    sorted_bodies = sorted(symbols_by_body.keys(), key=lambda k: (k[1] - k[0], k[0]))

    for byte, call_name in pending_calls:
        if call_name in {"if", "for", "while", "return"}:
            continue
        for key in sorted_bodies:
            start, end = key
            if start <= byte < end:
                sym = symbols_by_body[key]
                if call_name != sym.name and call_name not in sym.calls:
                    sym.calls.append(call_name)
                break

    # Attach extends to the enclosing class symbol when possible.
    unattached_extends: list[str] = []
    for byte, parent_name in pending_extends_with_pos:
        attached = False
        for key in sorted_bodies:
            start, end = key
            if start <= byte < end and symbols_by_body[key].kind == "class":
                sym = symbols_by_body[key]
                if parent_name not in sym.extends:
                    sym.extends.append(parent_name)
                attached = True
                break
        if not attached:
            unattached_extends.append(parent_name)

    if pending_imports or unattached_extends:
        module_symbol = Symbol(
            name=Path(path_str).stem,
            kind="module",
            line=1,
            language=language,
            path=path_str,
            imports=list(dict.fromkeys(pending_imports)),
            extends=list(dict.fromkeys(unattached_extends)),
        )
        return [module_symbol] + list(symbols_by_body.values())

    return list(symbols_by_body.values())
