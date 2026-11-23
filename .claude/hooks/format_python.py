"""PostToolUse hook: format and lint a Python file right after Claude edits it.

Silent when the file is clean. If lint errors remain after auto-fix, they are sent back to
Claude (exit code 2) so it fixes them immediately instead of at the end.
"""

import json
import subprocess
import sys


def main() -> int:
    payload = json.load(sys.stdin)
    path = str(payload.get("tool_input", {}).get("file_path", ""))
    if not path.endswith((".py", ".pyi")):
        return 0
    ruff = ["uv", "run", "--frozen", "ruff"]
    subprocess.run([*ruff, "format", "--quiet", path], check=False)
    result = subprocess.run(
        [*ruff, "check", "--fix", "--quiet", "--output-format=concise", path],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stdout[-3000:], file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
