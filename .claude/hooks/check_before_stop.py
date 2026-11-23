"""Stop hook: Claude cannot end its turn while Python changes break types or tests.

Runs only when uncommitted .py files exist, so plain questions cost nothing. Output is
trimmed to the tail so a failure does not flood the context.
"""

import subprocess
import sys

TAIL = 2500


def changed_python_files() -> bool:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return any(line.rstrip().endswith((".py", ".pyi")) for line in status.splitlines())


def run(name: str, cmd: list[str]) -> str | None:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return None
    return f"{name} failed:\n{(result.stdout + result.stderr)[-TAIL:]}"


def main() -> int:
    sys.stdin.read()
    if not changed_python_files():
        return 0
    py = ["uv", "run", "--frozen", "python", "-m"]
    failures = [
        f
        for f in (
            run("pyright", [*py, "pyright"]),
            run("pytest", [*py, "pytest", "-q", "-x", "--no-header"]),
        )
        if f
    ]
    if failures:
        print("\n\n".join(failures), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
