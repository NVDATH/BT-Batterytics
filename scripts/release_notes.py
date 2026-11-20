"""Write the release notes of one version.

Usage: python scripts/release_notes.py TAG CHANGELOG OUTPUT

If the changelog has "## <version>" headings, the notes are the section of the version of the tag,
so that one file can keep the history of every version.
If it has no such headings, the whole file is the notes of this release.
"""

import re
import sys
from pathlib import Path


def splitSections(text: str) -> list[tuple[str, str]]:
	parts = re.split(r"(?m)^## +(.*)$", text)
	return [(parts[i].strip(), parts[i + 1].strip("\n")) for i in range(1, len(parts) - 1, 2)]


def notesFor(text: str, tag: str) -> str:
	sections = splitSections(text)
	if not sections:
		return text.strip()
	full = tag.removeprefix("v")
	for version in (full, full.split("-", 1)[0]):
		for heading, body in sections:
			if re.match(rf"v?{re.escape(version)}(?:[\s(\[-]|$)", heading):
				return body.strip()
	return ""


def main() -> int:
	tag, changelog, output = sys.argv[1:4]
	path = Path(changelog)
	notes = notesFor(path.read_text(encoding="utf-8"), tag) if path.is_file() else ""
	Path(output).write_text((notes or f"Release {tag}") + "\n", encoding="utf-8", newline="\n")
	return 0


if __name__ == "__main__":
	sys.exit(main())
