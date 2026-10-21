# Copyright (c) 2026 Volodya1000
"""Run Import Linter with the project's src-layout package path configured."""

from __future__ import annotations

import asyncio
import os
import shutil
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

    async def run_linter() -> int:
        process = await asyncio.create_subprocess_exec(
            uvx_executable,
            "--from",
            "import-linter==2.15",
            "lint-imports",
            cwd=root,
            env=env,
        )
        return await process.wait()

    return asyncio.run(run_linter())


if __name__ == "__main__":
    raise SystemExit(main())
