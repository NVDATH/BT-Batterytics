"""Check the built add-on and the translation template against the sources.

Run it from the repository root, after `scons` and `scons pot`. It fails when:

- a file of the addon folder is missing from the .nvda-addon file;
- the .nvda-addon file holds compiled python files (__pycache__, .pyc);
- a python file calls _() or ngettext() but is not named in the .pot file, so its strings would never reach
  the translators (see pythonSources and i18nSources in buildVars.py).

These go wrong without any message when the shape of the add-on changes: a global plugin that becomes
a single file or a package, a sub-package, a sounds folder...
"""

import re
import sys
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path.cwd()))
import buildVars  # noqa: E402

ADDON_DIR = Path("addon")
TRANSLATABLE_CALL = re.compile(r"(?<![\w.])(?:_|ngettext|pgettext|npgettext)\(\s*[rbuf]*[\"']")


def isExcluded(relative: Path) -> bool:
	return any(relative.match(pattern) for pattern in buildVars.excludedFiles)


def shippedFiles() -> list[Path]:
	return sorted(
		path
		for path in ADDON_DIR.rglob("*")
		if path.is_file() and not isExcluded(path.relative_to(ADDON_DIR))
	)


def bundledNames(bundle: Path) -> set[str]:
	with zipfile.ZipFile(bundle) as archive:
		return {name for name in archive.namelist() if not name.endswith("/")}


def potReferences(pot: Path) -> set[str]:
	references: set[str] = set()
	for line in pot.read_text(encoding="utf-8").splitlines():
		if line.startswith("#:"):
			references.update(re.sub(r":\d+$", "", token).replace("\\", "/") for token in line[2:].split())
	return references


def findOne(pattern: str) -> Path | None:
	found = sorted(Path().glob(pattern))
	return found[0] if found else None


def main() -> int:
	bundle, pot = findOne("*.nvda-addon"), findOne("*.pot")
	if bundle is None or pot is None:
		print("::error::Build the add-on and the .pot file first: scons && scons pot")
		return 1
	problems: list[str] = []

	files = shippedFiles()
	expected = {path.relative_to(ADDON_DIR).as_posix() for path in files}
	actual = bundledNames(bundle)
	problems += [
		f"{name} is in the addon folder but not in {bundle.name}" for name in sorted(expected - actual)
	]
	problems += [
		f"{name} is in {bundle.name} but must not be (compiled python file)"
		for name in sorted(actual)
		if "__pycache__" in name.split("/") or name.endswith((".pyc", ".pyo"))
	]

	references = potReferences(pot)
	for path in files:
		if path.suffix != ".py":
			continue
		if TRANSLATABLE_CALL.search(path.read_text(encoding="utf-8")) and path.as_posix() not in references:
			problems.append(
				f"{path.as_posix()} has strings to translate but is not in {pot.name} (see i18nSources)",
			)

	for problem in problems:
		print(f"::error::{problem}")
	if not problems:
		print(f"{bundle.name}: {len(actual)} files, all the files of the addon folder are in it.")
		print(f"{pot.name}: every python file with strings to translate is covered.")
	return 1 if problems else 0


if __name__ == "__main__":
	sys.exit(main())
