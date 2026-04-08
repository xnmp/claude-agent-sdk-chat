"""Unit tests for SDK output folder hooks."""

from __future__ import annotations

import os
import tempfile

import pytest

from backend.infra.hooks import make_hooks


@pytest.fixture
def output_dir(tmp_path):
    d = tmp_path / "output"
    d.mkdir()
    return str(d)


@pytest.fixture
def hook_config(output_dir):
    return make_hooks(output_dir)


class TestEnforceOutputDir:
    async def test_allows_write_inside_output(self, hook_config, output_dir):
        hooks = hook_config["hooks"]
        enforce = hooks["PreToolUse"][0].hooks[0]

        result = await enforce(
            {"tool_input": {"file_path": os.path.join(output_dir, "test.txt")}},
            "tu-1",
            {"signal": None},
        )
        # Empty dict = no denial
        assert result.get("hookSpecificOutput") is None

    async def test_blocks_write_outside_output(self, hook_config, output_dir):
        enforce = hook_config["hooks"]["PreToolUse"][0].hooks[0]

        result = await enforce(
            {"tool_input": {"file_path": "/tmp/evil.txt"}},
            "tu-1",
            {"signal": None},
        )
        output = result.get("hookSpecificOutput", {})
        assert output.get("permissionDecision") == "deny"

    async def test_blocks_write_to_parent_dir(self, hook_config, output_dir):
        enforce = hook_config["hooks"]["PreToolUse"][0].hooks[0]
        parent = os.path.dirname(output_dir)

        result = await enforce(
            {"tool_input": {"file_path": os.path.join(parent, "escape.txt")}},
            "tu-1",
            {"signal": None},
        )
        assert result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"

    async def test_allows_empty_file_path(self, hook_config):
        enforce = hook_config["hooks"]["PreToolUse"][0].hooks[0]

        result = await enforce(
            {"tool_input": {"file_path": ""}},
            "tu-1",
            {"signal": None},
        )
        assert result == {}

    async def test_allows_no_file_path_key(self, hook_config):
        enforce = hook_config["hooks"]["PreToolUse"][0].hooks[0]

        result = await enforce(
            {"tool_input": {}},
            "tu-1",
            {"signal": None},
        )
        assert result == {}


class TestTrackCreatedFiles:
    async def test_tracks_file_in_output(self, hook_config, output_dir):
        track = hook_config["hooks"]["PostToolUse"][0].hooks[0]
        created_files = hook_config["created_files"]

        # Create the file so os.path.isfile returns True
        file_path = os.path.join(output_dir, "report.csv")
        with open(file_path, "w") as f:
            f.write("data")

        await track(
            {"tool_input": {"file_path": file_path}},
            "tu-1",
            {"signal": None},
        )
        assert "report.csv" in created_files

    async def test_ignores_file_outside_output(self, hook_config, output_dir):
        track = hook_config["hooks"]["PostToolUse"][0].hooks[0]
        created_files = hook_config["created_files"]

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"data")
            outside_path = f.name

        try:
            await track(
                {"tool_input": {"file_path": outside_path}},
                "tu-1",
                {"signal": None},
            )
            assert len(created_files) == 0
        finally:
            os.unlink(outside_path)

    async def test_ignores_nonexistent_file(self, hook_config, output_dir):
        track = hook_config["hooks"]["PostToolUse"][0].hooks[0]
        created_files = hook_config["created_files"]

        await track(
            {"tool_input": {"file_path": os.path.join(output_dir, "ghost.txt")}},
            "tu-1",
            {"signal": None},
        )
        assert len(created_files) == 0

    async def test_tracks_nested_file(self, hook_config, output_dir):
        track = hook_config["hooks"]["PostToolUse"][0].hooks[0]
        created_files = hook_config["created_files"]

        nested_dir = os.path.join(output_dir, "sub")
        os.makedirs(nested_dir)
        file_path = os.path.join(nested_dir, "deep.txt")
        with open(file_path, "w") as f:
            f.write("deep")

        await track(
            {"tool_input": {"file_path": file_path}},
            "tu-1",
            {"signal": None},
        )
        assert "sub/deep.txt" in created_files

    async def test_shared_set_between_hooks_and_config(self, hook_config, output_dir):
        """The created_files set must be the same object in both hooks and config."""
        track = hook_config["hooks"]["PostToolUse"][0].hooks[0]
        created_files = hook_config["created_files"]

        file_path = os.path.join(output_dir, "shared.txt")
        with open(file_path, "w") as f:
            f.write("test")

        await track(
            {"tool_input": {"file_path": file_path}},
            "tu-1",
            {"signal": None},
        )
        # The set returned by make_hooks is the same one the hook writes to
        assert "shared.txt" in created_files
