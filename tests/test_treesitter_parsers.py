"""Tree-sitter parsers for C/C++, Java and JS/TS.

Skipped automatically when no grammar is installed; the production code degrades
to windowed chunking in that case, which is covered by the parser tests.
"""

from __future__ import annotations

import pytest

from conftest import make_source
from repomind.models import ChunkType, Language
from repomind.treesitter_support import TreeSitterUnavailable, get_parser

GRAMMARS = {
    Language.C: "c",
    Language.CPP: "cpp",
    Language.JAVA: "java",
    Language.JAVASCRIPT: "javascript",
    Language.TYPESCRIPT: "typescript",
    Language.TSX: "tsx",
}


def require(language: Language) -> None:
    try:
        get_parser(GRAMMARS[language])
    except TreeSitterUnavailable:
        pytest.skip(f"no tree-sitter grammar for {GRAMMARS[language]}")


def symbols(chunks) -> set[str]:
    return {chunk.symbol for chunk in chunks}


def test_c_functions_and_structs() -> None:
    require(Language.C)
    from repomind import cpp_parser

    source = make_source(
        "#include <stdio.h>\n\nstruct Point { int x; int y; };\n\n"
        "static int add_numbers(int a, int b) {\n    return a + b;\n}\n",
        file_path="src/math.c",
        language=Language.C,
    )
    chunks = cpp_parser.parse(source)
    assert "add_numbers" in symbols(chunks)
    assert "Point" in symbols(chunks)


def test_cpp_class_methods_are_separate_chunks() -> None:
    require(Language.CPP)
    from repomind import cpp_parser

    source = make_source(
        "class Engine {\npublic:\n    void start() { running_ = true; }\n    void stop() { running_ = false; }\nprivate:\n    bool running_;\n};\n",
        file_path="src/engine.cpp",
        language=Language.CPP,
    )
    found = symbols(cpp_parser.parse(source))
    assert "Engine" in found
    assert any(name.endswith("start") for name in found)


def test_java_classes_methods_and_constructors() -> None:
    require(Language.JAVA)
    from repomind import java_parser

    source = make_source(
        "package app;\n\npublic class AuthService {\n    private final String secret;\n\n"
        "    public AuthService(String secret) { this.secret = secret; }\n\n"
        "    public boolean authenticate(String user) { return user != null; }\n}\n",
        file_path="src/AuthService.java",
        language=Language.JAVA,
    )
    chunks = java_parser.parse(source)
    kinds = {chunk.chunk_type for chunk in chunks}
    assert ChunkType.CLASS in kinds
    assert ChunkType.CONSTRUCTOR in kinds
    assert any("authenticate" in chunk.symbol for chunk in chunks)


def test_javascript_functions_and_arrow_consts() -> None:
    require(Language.JAVASCRIPT)
    from repomind import javascript_parser

    source = make_source(
        "export function login(user) {\n  return true;\n}\n\n"
        "const logout = (session) => {\n  session.destroy();\n};\n\nconst VERSION = 3;\n",
        file_path="src/auth.js",
        language=Language.JAVASCRIPT,
    )
    found = symbols(javascript_parser.parse(source))
    assert "login" in found
    assert "logout" in found
    assert "VERSION" not in found


def test_typescript_interfaces_are_captured() -> None:
    require(Language.TYPESCRIPT)
    from repomind import javascript_parser

    source = make_source(
        "export interface User {\n  id: string;\n  email: string;\n}\n\n"
        "export function findUser(id: string): User | null {\n  return null;\n}\n",
        file_path="src/user.ts",
        language=Language.TYPESCRIPT,
    )
    chunks = javascript_parser.parse(source)
    assert "User" in symbols(chunks)
    assert ChunkType.INTERFACE in {chunk.chunk_type for chunk in chunks}


def test_tsx_components_are_captured() -> None:
    require(Language.TSX)
    from repomind import javascript_parser

    source = make_source(
        "export function Panel({ title }: { title: string }) {\n  return <div>{title}</div>;\n}\n",
        file_path="src/Panel.tsx",
        language=Language.TSX,
    )
    assert "Panel" in symbols(javascript_parser.parse(source))


def test_line_ranges_are_one_indexed() -> None:
    require(Language.JAVA)
    from repomind import java_parser

    source = make_source(
        "public class A {\n    void method() {}\n}\n",
        file_path="A.java",
        language=Language.JAVA,
    )
    chunks = java_parser.parse(source)
    assert min(chunk.start_line for chunk in chunks) == 1
