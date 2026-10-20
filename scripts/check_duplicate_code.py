"""Fail when a changed Python file introduces a new duplicate-code pair.

Pylint runs against both the PR base and the current tree. Existing similarity
findings remain part of the baseline; only newly introduced pairs involving a
changed file fail the check.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

DUPLICATE_HEADING = "R0801: Similar lines in"


class ProcessResult(NamedTuple):
    """Captured output from an asynchronously started process."""

    returncode: int
    stdout: str
    stderr: str


def run_process(
    arguments: list[str], *, check: bool = False, cwd: Path | None = None
) -> ProcessResult:
    """Run an executable directly, capturing output without invoking a shell."""

    async def execute() -> ProcessResult:
        process = await asyncio.create_subprocess_exec(
            *arguments,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        return ProcessResult(
            process.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    result = asyncio.run(execute())
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}")
    return result


MODULE_LOCATION = re.compile(r"^==(.+?):\[(\d+):(\d+)\]$")


class DuplicatePair(NamedTuple):
    """A Pylint duplicate-code finding and both source locations."""

    heading: str
    first_module: str
    first_line: int
    second_module: str
    second_line: int


def git_executable() -> str:
    """Return the absolute path to Git or fail with an actionable error."""
    executable = shutil.which("git")
    if executable is None:
        raise RuntimeError
    return executable


class EventPayloadReadError(RuntimeError):
    """GitHub event metadata could not be read."""

    def __init__(self) -> None:
        super().__init__(
            "Unable to read the GitHub event payload for duplicate-code check"
        )


class InvalidEventPayloadError(RuntimeError):
    """GitHub event metadata has an unexpected structure."""

    def __init__(self) -> None:
        super().__init__("GitHub event payload must be a JSON object")


class PylintBaselineCheckError(RuntimeError):
    """Pylint could not inspect the baseline revision."""

    def __init__(self) -> None:
        super().__init__("Pylint failed while checking the baseline revision")


def git_output(arguments: list[str]) -> str:
    """Run Git and return standard output."""
    result = run_process(
        arguments,
        check=True,
    )
    return result.stdout.strip()


def changed_files_from_git() -> set[str] | None:
    """Return files changed in the current CI event, or None locally."""
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if base_ref:
        base = git_output(
            [git_executable(), "merge-base", f"origin/{base_ref}", "HEAD"]
        )
        changed = git_output([git_executable(), "diff", "--name-only", base, "HEAD"])
        return {Path(path).as_posix() for path in changed.splitlines() if path}

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path:
        try:
            event_payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EventPayloadReadError from error

        if not isinstance(event_payload, dict):
            raise InvalidEventPayloadError

        before = event_payload.get("before")
        if isinstance(before, str) and before:
            if set(before) == {"0"}:
                changed = git_output(
                    [git_executable(), "ls-tree", "-r", "--name-only", "HEAD"]
                )
            else:
                changed = git_output(
                    [git_executable(), "diff", "--name-only", before, "HEAD"]
                )
            return {Path(path).as_posix() for path in changed.splitlines() if path}

    # Compatibility fallback for custom CI environments that export this value.
    before = os.environ.get("GITHUB_EVENT_BEFORE")
    if before and set(before) != {"0"}:
        changed = git_output([git_executable(), "diff", "--name-only", before, "HEAD"])
        return {Path(path).as_posix() for path in changed.splitlines() if path}

    return None


def module_to_path(module_name: str) -> str:
    """Map a Pylint module name or file path to a repository-relative path."""
    normalized_name = module_name.replace("\\", "/")
    if normalized_name.endswith(".py"):
        return Path(normalized_name).as_posix()

    parts = normalized_name.split(".")

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

    # Retain a deterministic fallback for module names absent from the tree.
    root = parts.pop(0) if parts[0] in {"tests", "scripts"} else "src"
    if parts and parts[-1] == "__init__":
        parts.pop()
        filename = "__init__.py"
    else:
        filename = f"{parts.pop()}.py" if parts else "__init__.py"

    return Path(root).joinpath(*parts, filename).as_posix()


def duplicate_pairs(output: str) -> list[DuplicatePair]:
    """Extract file pairs and line locations reported by Pylint."""
    lines = output.splitlines()
    pairs: list[DuplicatePair] = []

    for index, line in enumerate(lines):
        if DUPLICATE_HEADING not in line:
            continue

        modules: list[tuple[str, int]] = []
        for candidate in lines[index + 1 :]:
            if "R0801:" in candidate:
                break
            match = MODULE_LOCATION.match(candidate.strip())
            if match:
                modules.append((match.group(1), int(match.group(2))))
                if len(modules) == 2:
                    break

        if len(modules) == 2:
            pairs.append(
                DuplicatePair(
                    line,
                    modules[0][0],
                    modules[0][1],
                    modules[1][0],
                    modules[1][1],
                )
            )

    return pairs


def pylint_output(cwd: Path | None = None) -> tuple[int, str]:
    """Run the duplicate-code checker and return its exit status and output."""
    result = run_process(
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
        cwd=cwd,
    )
    return result.returncode, result.stdout + result.stderr


def pair_key(pair: DuplicatePair) -> tuple[str, str]:
    """Normalize a duplicate finding to its two repository-relative paths."""
    _, first_module, _, second_module, _ = pair
    first_path = module_to_path(first_module)
    second_path = module_to_path(second_module)
    return (min(first_path, second_path), max(first_path, second_path))


def changed_line_numbers(base: str, path: str) -> set[int]:
    """Return added or modified line numbers relative to the comparison base."""
    diff = git_output(
        [git_executable(), "diff", "--unified=0", base, "HEAD", "--", path]
    )
    changed_lines: set[int] = set()
    hunk_pattern = re.compile(r"^@@ -[0-9]+(?:,[0-9]+)? \+([0-9]+)(?:,([0-9]+))? @@")
    for line in diff.splitlines():
        match = hunk_pattern.match(line)
        if match is None:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        changed_lines.update(range(start, start + count))
    return changed_lines


def baseline_duplicate_pairs(base: str) -> set[tuple[str, str]]:
    """Return duplicate pairs already present at the comparison base."""
    with tempfile.TemporaryDirectory(prefix="asd-duplicate-baseline-") as directory:
        baseline = Path(directory) / "baseline"
        run_process(
            [
                git_executable(),
                "worktree",
                "add",
                "--detach",
                "--quiet",
                str(baseline),
                base,
            ],
            check=True,
        )
        try:
            returncode, output = pylint_output(baseline)
            if returncode & ~8:
                print(output)
                raise PylintBaselineCheckError
            return {pair_key(pair) for pair in duplicate_pairs(output)}
        finally:
            run_process(
                [
                    git_executable(),
                    "worktree",
                    "remove",
                    "--force",
                    str(baseline),
                ],
                check=False,
            )


def new_duplicate_finding(
    pair: DuplicatePair,
    changed: set[str],
    baseline_pairs: set[tuple[str, str]],
    base: str | None,
) -> str | None:
    """Format a duplicate finding only when its changed source line is new."""
    first_path = module_to_path(pair.first_module)
    second_path = module_to_path(pair.second_module)
    if pair_key(pair) in baseline_pairs:
        return None
    if first_path not in changed and second_path not in changed:
        return None

    first_changed = first_path in changed and (
        base is None or pair.first_line in changed_line_numbers(base, first_path)
    )
    second_changed = second_path in changed and (
        base is None or pair.second_line in changed_line_numbers(base, second_path)
    )
    if not (first_changed or second_changed):
        return None

    return (
        f"{pair.heading}\n"
        f"  {first_path}:{pair.first_line}\n"
        f"  {second_path}:{pair.second_line}"
    )


def main() -> int:
    """Fail only when a changed file introduces a new duplicate-code pair."""
    base_ref = os.environ.get("GITHUB_BASE_REF")
    changed = changed_files_from_git()
    if changed is None:
        changed = {
            Path(path).as_posix() for path in sys.argv[1:] if path.endswith(".py")
        }

    if not changed:
        print("No changed Python files; duplicate-code check skipped.")
        return 0

    returncode, output = pylint_output()
    # R0801 is a refactor message (exit-code bit 8) and is handled below.
    # Other exit-code bits indicate a failed/invalid lint run and must fail CI.
    if returncode & ~8:
        print(output)
        return 1

    current_pairs = duplicate_pairs(output)
    base: str | None = None
    baseline_pairs: set[tuple[str, str]] = set()
    if base_ref:
        base = git_output(
            [git_executable(), "merge-base", f"origin/{base_ref}", "HEAD"]
        )
        baseline_pairs = baseline_duplicate_pairs(base)

    failures: list[str] = []
    for pair in current_pairs:
        failure = new_duplicate_finding(pair, changed, baseline_pairs, base)
        if failure is not None:
            failures.append(failure)

    if failures:
        print("\n".join(failures))
        return 1

    print("No new duplicate-code findings in changed Python files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
