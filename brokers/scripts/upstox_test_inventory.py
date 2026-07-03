"""Generate archived→modern Upstox test traceability inventory."""

from __future__ import annotations

import re
from pathlib import Path

ARCHIVE_TESTS = Path("archive/brokers/upstox/tests")
MODERN_TESTS = Path("brokers/tests")


def _test_functions(path: Path) -> list[str]:
    if not path.exists():
        return []
    return re.findall(r"^\s*def (test_\w+)", path.read_text(), re.MULTILINE)


def main() -> None:
    archive_files = sorted(ARCHIVE_TESTS.rglob("test_*.py"))
    modern_files = sorted(MODERN_TESTS.rglob("*upstox*.py")) + sorted(
        (MODERN_TESTS / "unit/adapters/upstox").rglob("test_*.py")
    )
    modern_names = {f.name for f in modern_files}

    print(f"Archive test files: {len(archive_files)}")
    print(f"Archive test functions: {sum(len(_test_functions(f)) for f in archive_files)}")
    print(f"Modern upstox test files: {len(modern_files)}")
    print(f"Modern test functions: {sum(len(_test_functions(f)) for f in modern_files)}")
    print()
    print("Archive files without modern name match:")
    for f in archive_files:
        if f.name not in modern_names:
            print(f"  - {f.relative_to(ARCHIVE_TESTS)} ({len(_test_functions(f))} tests)")


if __name__ == "__main__":
    main()
