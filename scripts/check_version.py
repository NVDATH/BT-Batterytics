"""Check the version of the add-on before it is built or released.

Usage: python scripts/check_version.py [TAG]

With a tag (for example v0.5.0, or 0.5.0-beta1), the tag must say the same version as buildVars.py.
The NVDA Add-on Store reads the version from the manifest, so a tag that disagrees with it would publish
a build under the wrong version. A part after the first "-" of the tag is ignored.

Without a tag, only the format is checked. A version that is not major.minor.patch is reported as a warning,
because the NVDA Add-on Store works with three numbers.
"""

import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
# buildVars.py is in the repository root, which is not where this script lives.
sys.path.insert(0, str(Path.cwd()))
import buildVars  # noqa: E402


def main() -> int:
	version = str(buildVars.addon_info["addon_version"])
	tag = sys.argv[1].strip() if len(sys.argv) > 1 else ""
	if tag:
		tagVersion = tag.removeprefix("v").split("-", 1)[0]
		if tagVersion != version:
			print(f"::error::The tag {tag} says version {tagVersion}, but buildVars.py says {version}.")
			return 1
		print(f"The tag {tag} matches the version {version}.")
	if not re.fullmatch(r"\d+\.\d+\.\d+", version):
		print(
			f"::warning::The version {version} is not of the form major.minor.patch, such as 0.5.0, "
			"which the NVDA Add-on Store works with.",
		)
	return 0


if __name__ == "__main__":
	sys.exit(main())
