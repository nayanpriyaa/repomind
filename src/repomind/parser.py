import ast
from pathlib import Path
from repomind.models import CodeChunk

class PythonASTChunker(ast.NodeVisitor):

    def __init__(self, source_code: str, file_path: Path):
        self.source_code = source_code
        self.file_path = file_path
        self.chunks: list[CodeChunk] = []
        self._class_stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_stack.append(node.name)

        self._add_chunk(
            node=node,
            chunk_type="CLASS",
            name=node.name,
        )

        self.generic_visit(node)

        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._class_stack:
            chunk_type = "METHOD"
        else:
            chunk_type = "FUNCTION"

        self._add_chunk(
            node=node,
            chunk_type=chunk_type,
            name=node.name,
        )

        self.generic_visit(node)

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        if self._class_stack:
            chunk_type = "METHOD"
        else:
            chunk_type = "FUNCTION"

        self._add_chunk(
            node=node,
            chunk_type=chunk_type,
            name=node.name,
        )

        self.generic_visit(node)

    def _add_chunk(
        self,
        node: ast.AST,
        chunk_type: str,
        name: str,
) -> None:
      start_line = self._get_start_line(node)
      end_line = node.end_lineno

      lines = self.source_code.splitlines()

      content = "\n".join(
          lines[start_line - 1:end_line]
    )

      self.chunks.append(
          CodeChunk(
              file_path=self.file_path,
              chunk_type=chunk_type,
              name=name,
              start_line=start_line,
              end_line=end_line,
              content=content,
        )
    )
    def _get_start_line(self, node: ast.AST) -> int:
        decorator_lines = getattr(node, "decorator_list", [])

        if decorator_lines:
            return min(
                decorator.lineno
                for decorator in decorator_lines
            )

        return node.lineno


def parse_python_file(file_path: Path) -> list[CodeChunk]:
    source_code = file_path.read_text(encoding="utf-8")

    tree = ast.parse(
        source_code,
        filename=str(file_path),
    )

    chunker = PythonASTChunker(
        source_code=source_code,
        file_path=file_path,
    )

    chunker.visit(tree)

    return chunker.chunks