"""Read static prompt strings from locked paper source without importing API code."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / 'external'


def constant(repo: str, path: str, name: str) -> str:
    source = ROOT / repo / path
    tree = ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
    raise ValueError(f'Static prompt {name} not found in {source}')


def isolated_function(repo: str, path: str, name: str):
    """Load a pure prompt builder without executing the source module imports."""
    source = ROOT / repo / path
    tree = ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(functions) != 1:
        raise ValueError(f'Prompt function {name} not found in {source}')
    namespace = {}
    code = compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec')
    exec(code, namespace)
    return namespace[name]
