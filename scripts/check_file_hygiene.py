"""Read-only checks for repository whitespace and end-of-file hygiene."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

_logger = logging.getLogger(__name__)


def tracked_files() -> list[Path]:
    """Return paths tracked by Git, including staged additions."""
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError

    async def list_tracked_files() -> bytes:
        process = await asyncio.create_subprocess_exec(
            git_executable,
            "ls-files",
            "-z",
            stdout=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            message = "Git could not list tracked files"
            raise RuntimeError(message)
        return stdout

    output = asyncio.run(list_tracked_files())
    return [
        Path(raw_path.decode("utf-8")) for raw_path in output.split(b"\0") if raw_path
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
        _logger.error("%s", "\n".join(failures))
        return 1

    _logger.info("Whitespace and EOF checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
