"""The structure of the package: what NVDA needs to load it, and no import that goes round in a circle."""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "addon" / "globalPlugins" / "btBatterytics"
MODULES = sorted(PACKAGE.glob("*.py"))


def _tree(path):
	return ast.parse(path.read_text(encoding="utf-8"))


def test_the_package_gives_NVDA_its_global_plugin(bt):
	# NVDA imports globalPlugins.<name> and takes GlobalPlugin from it.
	assert hasattr(bt.package, "GlobalPlugin")


def test_every_module_with_translatable_strings_starts_the_translation():
	# NVDA puts _ in the module that calls addonHandler.initTranslation(): each module needs its own call.
	for path in MODULES:
		tree = _tree(path)
		calls = [
			node.lineno
			for node in tree.body
			if isinstance(node, ast.Expr) and ast.unparse(node.value) == "addonHandler.initTranslation()"
		]
		first_use = min(
			(
				node.lineno
				for node in ast.walk(tree)
				if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_"
			),
			default=None,
		)
		if first_use is None:
			continue
		assert calls, f"{path.name} uses _ but does not call initTranslation()"
		assert calls[0] < first_use, f"{path.name} uses _ before initTranslation()"


def test_modules_do_not_import_each_other_in_a_circle():
	graph = {}
	for path in MODULES:
		name = path.stem
		graph[name] = set()
		for node in _tree(path).body:
			if isinstance(node, ast.ImportFrom) and node.level == 1:
				if node.module:
					graph[name].add(node.module)
				else:
					graph[name].update(alias.name for alias in node.names)

	def visit(name, path):
		assert name not in path, f"circular import: {' -> '.join([*path, name])}"
		for other in graph.get(name, ()):
			if other in graph:
				visit(other, [*path, name])

	for name in graph:
		visit(name, [])
	# Only the package itself may import everything: the other modules never import from it.
	for name, imports in graph.items():
		if name != "__init__":
			assert "__init__" not in imports
