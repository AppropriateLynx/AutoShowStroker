"""Blocks a Write/Edit that leaves a Python file syntactically broken.

Run with the project venv interpreter (see .claude/settings.json), not the bare PATH
python: validating against a different Python than the one the project actually runs on
is worse than not validating at all - it both rejects valid syntax and misses nothing
useful. This repo targets 3.13; the PATH python on the maintainer's machine is 3.10.

Uses compile() rather than py_compile so no __pycache__/*.pyc is written as a side
effect - those artifacts are what made the version mismatch confusing to track down.
"""

import json
import sys
from pathlib import Path


def main():
    payload = json.load(sys.stdin)
    file_path = payload.get("tool_input", {}).get("file_path", "")

    if not file_path.endswith(".py"):
        return

    try:
        source = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return  # nothing to check - the tool itself will have reported the real problem

    try:
        compile(source, file_path, "exec")
    except SyntaxError as error:
        print(json.dumps({
            "decision": "block",
            "reason": f"Syntax error in {file_path}:\n{error}",
        }))


if __name__ == "__main__":
    main()
