"""Fail closed if a built ccm-casework wheel omits code or includes repository artifacts."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def main() -> None:
    wheels = sorted(DIST.glob("ccm_casework-*.whl"))
    if len(wheels) != 1:
        raise SystemExit("expected exactly one ccm_casework wheel")
    with ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
    required = {
        "ccm_casework/__init__.py",
        "ccm_casework/canonical.py",
        "ccm_casework/evaluator.py",
        "ccm_casework/models.py",
    }
    missing = sorted(required - names)
    if missing:
        raise SystemExit(f"wheel missing expected files: {', '.join(missing)}")
    forbidden = sorted(
        name for name in names if name.startswith(("tests/", "fixtures/", ".github/"))
    )
    if forbidden:
        raise SystemExit(f"wheel contains non-package artifacts: {', '.join(forbidden)}")
    print(f"VALID wheel={wheels[0].name} files={len(names)}")


if __name__ == "__main__":
    main()
