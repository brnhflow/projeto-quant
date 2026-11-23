"""Smoke test: proves the toolchain (install, import, pytest, mypy) is wired up.

Delete it once the first real module has its own tests.
"""

import quant


def test_package_imports_and_has_version() -> None:
    assert quant.__version__ == "0.0.1"
