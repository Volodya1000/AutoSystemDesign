"""Read-only checks for repository whitespace and end-of-file hygiene."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def tracked_files() -> list[Path]:
    """Return paths tracked by Git, including staged additions."""
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("Git is required")

    result = subprocess.run(
        [git_executable, "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [
        Path(raw_path.decode("utf-8"))
        for raw_path in result.stdout.split(b"\0")
        if raw_path
    ]


def main() -> int:
    """Check tracked UTF-8 files without modifying them."""
    failures: list[str] = []

    for path in tracked_files():
        try:
            content = path.read_bytes()
            text = content.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        if content and not content.endswith(b"\n"):
            failures.append(f"{path}: missing newline at end of file")
        elif content.endswith(b"\n\n"):
            failures.append(f"{path}: extra blank lines at end of file")

        for line_number, line in enumerate(text.splitlines(), start=1):
            if line.endswith((" ", "\t")):
                failures.append(f"{path}:{line_number}: trailing whitespace")

    if failures:
        print("\n".join(failures))
        return 1

    print("Whitespace and EOF checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
