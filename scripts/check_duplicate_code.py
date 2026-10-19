"""Fail only on duplicate-code findings involving changed Python files.

The repository already contains legacy similarity findings. Keep the Pylint
rule enabled, but make it incremental so unrelated changes are not blocked by
pre-existing duplication elsewhere in the codebase.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

DUPLICATE_HEADING = "R0801: Similar lines in"
MODULE_LOCATION = re.compile(r"^==(.+?):\[(\d+):(\d+)\]$")


def git_output(arguments: list[str]) -> str:
    """Run Git and return standard output."""
    result = subprocess.run(
        arguments,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def changed_files_from_git() -> set[str] | None:
    """Return files changed in the current CI event, or None locally."""
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if base_ref:
        base = git_output(["git", "merge-base", f"origin/{base_ref}", "HEAD"])
        changed = git_output(["git", "diff", "--name-only", base, "HEAD"])
        return {Path(path).as_posix() for path in changed.splitlines() if path}

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path:
        try:
            event_payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(
                "Unable to read the GitHub event payload for duplicate-code check"
            ) from error

        if not isinstance(event_payload, dict):
            raise RuntimeError("GitHub event payload must be a JSON object")

        before = event_payload.get("before")
        if isinstance(before, str) and before:
            if set(before) == {"0"}:
                changed = git_output(["git", "ls-tree", "-r", "--name-only", "HEAD"])
            else:
                changed = git_output(["git", "diff", "--name-only", before, "HEAD"])
            return {Path(path).as_posix() for path in changed.splitlines() if path}

    # Compatibility fallback for custom CI environments that export this value.
    before = os.environ.get("GITHUB_EVENT_BEFORE")
    if before and set(before) != {"0"}:
        changed = git_output(["git", "diff", "--name-only", before, "HEAD"])
        return {Path(path).as_posix() for path in changed.splitlines() if path}

    return None


def module_to_path(module_name: str) -> str:
    """Map a Pylint module name to its repository-relative Python path."""
    parts = module_name.split(".")

    for root in ("tests", "scripts", "src"):
        relative_parts = parts[1:] if parts[0] == root else parts
        if not relative_parts:
            continue

        module_path = Path(root, *relative_parts)
        module_file = module_path.with_suffix(".py")
        if module_file.is_file():
            return module_file.as_posix()

        package_file = module_path / "__init__.py"
        if package_file.is_file():
            return package_file.as_posix()

    # Retain a deterministic fallback for paths absent from the working tree.
    root = parts.pop(0) if parts[0] in {"tests", "scripts"} else "src"
    if parts and parts[-1] == "__init__":
        parts.pop()
        filename = "__init__.py"
    else:
        filename = f"{parts.pop()}.py" if parts else "__init__.py"

    return Path(root).joinpath(*parts, filename).as_posix()


def duplicate_pairs(output: str) -> list[tuple[str, str, str]]:
    """Extract file pairs reported by Pylint's duplicate-code checker."""
    lines = output.splitlines()
    pairs: list[tuple[str, str, str]] = []

    for index, line in enumerate(lines):
        if DUPLICATE_HEADING not in line:
            continue

        modules: list[str] = []
        for candidate in lines[index + 1 :]:
            if "R0801:" in candidate:
                break
            match = MODULE_LOCATION.match(candidate.strip())
            if match:
                modules.append(match.group(1))
                if len(modules) == 2:
                    break

        if len(modules) == 2:
            pairs.append((line, modules[0], modules[1]))

    return pairs


def main() -> int:
    """Report duplicate code only when at least one involved file changed."""
    changed = changed_files_from_git()
    if changed is None:
        changed = {
            Path(path).as_posix() for path in sys.argv[1:] if path.endswith(".py")
        }

    if not changed:
        print("No changed Python files; duplicate-code check skipped.")
        return 0

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pylint",
            "--disable=all",
            "--enable=duplicate-code",
            "--output-format=text",
            "src",
            "tests",
            "scripts",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    # R0801 is a refactor message (exit-code bit 8) and is handled below.
    # Other exit-code bits indicate a failed/invalid lint run and must fail CI.
    if result.returncode & ~8:
        print(output)
        return 1

    failures: list[str] = []
    for heading, first_module, second_module in duplicate_pairs(output):
        first_path = module_to_path(first_module)
        second_path = module_to_path(second_module)
        if first_path in changed or second_path in changed:
            failures.append(f"{heading}\n  {first_path}\n  {second_path}")

    if failures:
        print("\n".join(failures))
        return 1

    print("No new duplicate-code findings in changed Python files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
