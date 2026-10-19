"""Run Import Linter with the project's src-layout package path configured."""

from __future__ import annotations

import os
import subprocess
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

    result = subprocess.run(
        ["uvx", "--from", "import-linter==2.15", "lint-imports"],
        cwd=root,
        env=env,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
