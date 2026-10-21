"""Run Import Linter with the project's src-layout package path configured."""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    """Run the pinned Import Linter CLI without changing the environment."""
    root = Path(__file__).resolve().parents[1]
    source_root = str(root / "src")
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        path for path in (source_root, existing_pythonpath) if path
    )

    uvx_executable = shutil.which("uvx")
    if uvx_executable is None:
        raise RuntimeError

    return asyncio.run(_run_linter(uvx_executable, root, env))


async def _run_linter(
    executable: str, root: Path, environment: dict[str, str]
) -> int:
    """Launch import-linter with the repository's Python import path."""
    process = await asyncio.create_subprocess_exec(
        executable,
        "--from",
        "import-linter==2.15",
        "lint-imports",
        cwd=root,
        env=environment,
    )
    return await process.wait()


if __name__ == "__main__":
    sys.exit(main())
