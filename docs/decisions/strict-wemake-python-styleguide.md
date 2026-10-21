# Strict Wemake Python Styleguide

The project runs [wemake-python-styleguide](https://github.com/wemake-services/wemake-python-styleguide) **1.8.1** with Python 3.13. WPS supplements Ruff and runs independently of mypy, pylint, pytest and import-linter.

Run from the repository root:

```bash
uvx --python 3.13 --from wemake-python-styleguide==1.8.1 flake8 src tests scripts --select=WPS
uv run pre-commit run wemake-python-styleguide --all-files
```

Both the local pre-commit hook and CI check **all** project Python code, including tests and scripts. Neither check accepts an existing-violations baseline. A violation fails the check.

WPS options are in `setup.cfg`. WPS suppression via `noqa` is explicitly forbidden. Never mask a violation using `noqa`, `ignore`, `extend-ignore`, `per-file-ignores`, a file exclusion, a reduced set of checks, or a non-failing exit code. Refactor the offending code and retain runtime behavior and type annotations.

`uvx --from` installs a pinned standalone lint tool. This keeps the application dependency graph and its `uv.lock` unchanged, without compromising repeatability of the WPS version. Use `uv run` for the remaining checks.

Inline suppressions are rejected by `scripts/check_lint_suppressions.py`, which tokenizes Python comments rather than matching strings in test fixtures. It detects `noqa`, `type: ignore`, `pylint: disable`, `nosec`, coverage and Pyright suppression directives. The guard runs independently in CI and pre-commit.
