from __future__ import annotations

import pytest

from cortex_claude.code import extract_symbols, is_supported_path


class TestIsSupported:
    @pytest.mark.parametrize("path", [
        "x.py", "x.js", "x.mjs", "x.ts", "x.tsx", "x.go", "x.java", "x.swift", "x.kt",
    ])
    def test_supported_extensions(self, path):
        assert is_supported_path(path) is True

    @pytest.mark.parametrize("path", ["x.txt", "x.md", "x", "x.rs", "Makefile"])
    def test_unsupported_extensions(self, path):
        assert is_supported_path(path) is False


class TestExtractor:
    def test_python(self):
        src = """
import json
from pathlib import Path

class Greeter(Base):
    def hello(self):
        return self.format()

    def format(self):
        return json.dumps({})
"""
        syms = extract_symbols("g.py", src)
        names = {s.name for s in syms}
        assert "Greeter" in names
        assert "hello" in names
        assert "format" in names

        greeter = next(s for s in syms if s.name == "Greeter")
        assert greeter.kind == "class"
        assert "Base" in greeter.extends

        hello = next(s for s in syms if s.name == "hello")
        assert "format" in hello.calls

        module = next(s for s in syms if s.kind == "module")
        assert "json" in module.imports
        assert "pathlib" in module.imports

    def test_javascript(self):
        src = """
import { x } from "./other";
class Foo { hello() { return this.process(); } }
function standalone() { new Foo().hello(); }
"""
        syms = extract_symbols("f.js", src)
        names = {s.name for s in syms}
        assert "Foo" in names
        assert "hello" in names
        assert "standalone" in names

    def test_typescript_interface(self):
        src = """
interface Greeter { hello(): string; }
class Foo implements Greeter { hello(): string { return "hi"; } }
"""
        syms = extract_symbols("f.ts", src)
        names = {s.name for s in syms}
        assert "Greeter" in names
        assert "Foo" in names

    def test_go(self):
        src = """
package main
import "fmt"
type Foo struct { Name string }
func (f *Foo) Hello() string { return f.process() }
func main() { fmt.Println("hi") }
"""
        syms = extract_symbols("f.go", src)
        names = {s.name for s in syms}
        assert "Foo" in names
        assert "Hello" in names
        assert "main" in names

    def test_java(self):
        src = """
package com.example;
import java.util.List;
public class Foo {
    public String hello() { return process(); }
    private String process() { return "hi"; }
}
"""
        syms = extract_symbols("F.java", src)
        names = {s.name for s in syms}
        assert "Foo" in names
        assert "hello" in names
        assert "process" in names

    def test_swift(self):
        src = """
import Foundation
class Foo {
    func hello() -> String { return process() }
    func process() -> String { return "hi" }
}
"""
        syms = extract_symbols("F.swift", src)
        names = {s.name for s in syms}
        assert "Foo" in names
        assert "hello" in names
        assert "process" in names

    def test_kotlin(self):
        src = """
package com.example
class Foo {
    fun hello(): String = process()
    fun process(): String = "hi"
}
"""
        syms = extract_symbols("F.kt", src)
        names = {s.name for s in syms}
        assert "Foo" in names
        assert "hello" in names
        assert "process" in names

    def test_unsupported_returns_empty(self):
        assert extract_symbols("x.txt", "anything") == []

    def test_invalid_syntax_doesnt_crash(self):
        syms = extract_symbols("x.py", "def hello(\n    not valid python")
        assert isinstance(syms, list)

    def test_calls_attributed_to_innermost_scope(self):
        """The class shouldn't claim calls that belong to its methods."""
        src = """
class Foo:
    def method_one(self):
        return helper_a()

    def method_two(self):
        return helper_b()
"""
        syms = extract_symbols("x.py", src)
        foo = next(s for s in syms if s.name == "Foo")
        m1 = next(s for s in syms if s.name == "method_one")
        m2 = next(s for s in syms if s.name == "method_two")
        assert "helper_a" in m1.calls
        assert "helper_b" in m2.calls
        assert "helper_a" not in foo.calls
        assert "helper_b" not in foo.calls
