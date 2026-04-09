"""SDK hooks — enforce directory constraints, track created files, limit reads."""

from __future__ import annotations

import os
from typing import Any

MAX_READ_BYTES = 100_000  # 100KB


def make_hooks(
    output_dir: str,
    scripts_dir: str,
    uploads_dir: str,
) -> dict:
    """Create SDK hook config.

    Args:
        output_dir: Where downloadable output files go.
        scripts_dir: Where intermediate scripts/code can be written (not downloaded).
        uploads_dir: Where user uploads are stored (read-only for agent).

    Returns a hooks dict suitable for ClaudeAgentOptions.hooks, plus a
    reference to the created_files set for retrieval after a turn.
    """
    created_files: set[str] = set()

    writable_dirs = [os.path.realpath(d) for d in [output_dir, scripts_dir]]
    readable_dirs = [os.path.realpath(d) for d in [output_dir, scripts_dir, uploads_dir]]
    abs_output = os.path.realpath(output_dir)

    def _is_under(path: str, allowed: list[str]) -> bool:
        real = os.path.realpath(path)
        return any(real.startswith(d + os.sep) or real == d for d in allowed)

    async def enforce_write_dirs(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if not file_path:
            return {}
        if not _is_under(file_path, writable_dirs):
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"File writes must be under output/ or output_scripts/. "
                        f"Got: {file_path}"
                    ),
                }
            }
        return {}

    async def enforce_read_dirs(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if not file_path:
            return {}
        if not _is_under(file_path, readable_dirs):
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"Can only read files from output/, output_scripts/, or uploads/. "
                        f"Got: {file_path}"
                    ),
                }
            }
        return {}

    async def limit_read_size(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
        if not file_path:
            return {}
        try:
            size = os.path.getsize(os.path.realpath(file_path))
        except OSError:
            return {}
        if tool_input.get("limit") or tool_input.get("offset"):
            return {}
        if size > MAX_READ_BYTES:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"File is {size:,} bytes (limit: {MAX_READ_BYTES:,}). "
                        f"Use 'limit' and 'offset' parameters to read a portion, "
                        f"or use Bash with head/tail to inspect it."
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
            real = os.path.realpath(file_path)
            # Only track files in output/ (not output_scripts/)
            if real.startswith(abs_output + os.sep) and os.path.isfile(real):
                rel = os.path.relpath(real, abs_output)
                created_files.add(rel)
        return {}

    # Snapshot of output/ files before each Bash command
    bash_snapshot: set[str] = set()

    def _scan_output() -> set[str]:
        found: set[str] = set()
        for root, _dirs, files in os.walk(abs_output):
            for fname in files:
                full = os.path.join(root, fname)
                found.add(os.path.relpath(full, abs_output))
        return found

    async def snapshot_output_before_bash(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Snapshot output/ before Bash so we can diff after."""
        bash_snapshot.clear()
        bash_snapshot.update(_scan_output())
        return {}

    async def diff_output_after_bash(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """After Bash, track any new files in output/."""
        current = _scan_output()
        new_files = current - bash_snapshot
        created_files.update(new_files)
        return {}

    from claude_agent_sdk import HookMatcher

    hooks = {
        "PreToolUse": [
            HookMatcher(matcher="Write|Edit", hooks=[enforce_write_dirs]),  # type: ignore[list-item]
            HookMatcher(matcher="Read", hooks=[enforce_read_dirs, limit_read_size]),  # type: ignore[list-item]
            HookMatcher(matcher="Bash", hooks=[snapshot_output_before_bash]),  # type: ignore[list-item]
        ],
        "PostToolUse": [
            HookMatcher(matcher="Write|Edit", hooks=[track_created_files]),  # type: ignore[list-item]
            HookMatcher(matcher="Bash", hooks=[diff_output_after_bash]),  # type: ignore[list-item]
        ],
    }

    return {"hooks": hooks, "created_files": created_files}
