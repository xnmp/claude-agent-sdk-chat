"""SDK hooks — enforce output folder constraints and track created files."""

from __future__ import annotations

import os
from typing import Any


def make_hooks(output_dir: str) -> dict:
    """Create SDK hook config that enforces writes to output_dir and tracks created files.

    Returns a hooks dict suitable for ClaudeAgentOptions.hooks, plus a
    reference to the created_files set for retrieval after a turn.
    """
    created_files: set[str] = set()
    abs_output = os.path.realpath(output_dir)

    # Hook inputs arrive as plain dicts, not typed dataclasses.

    async def enforce_output_dir(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if not file_path:
            return {}

        abs_path = os.path.realpath(file_path)
        if not abs_path.startswith(abs_output + os.sep) and abs_path != abs_output:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"File writes must be under {output_dir}/. "
                        f"Got: {file_path}"
                    ),
                }
            }
        return {}

    async def track_created_files(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if file_path:
            abs_path = os.path.realpath(file_path)
            if abs_path.startswith(abs_output + os.sep) and os.path.isfile(abs_path):
                rel = os.path.relpath(abs_path, abs_output)
                created_files.add(rel)
        return {}

    from claude_agent_sdk import HookMatcher

    hooks = {
        "PreToolUse": [HookMatcher(matcher="Write|Edit", hooks=[enforce_output_dir])],
        "PostToolUse": [HookMatcher(matcher="Write|Edit", hooks=[track_created_files])],
    }

    return {"hooks": hooks, "created_files": created_files}
