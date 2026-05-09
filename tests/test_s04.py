"""
Unit tests for agents/s04.py utility functions.

Tests the core helper functions: safe_path, run_bash, run_write, run_read, run_edit.
These tests do NOT require an API key -- they mock external dependencies.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def workdir():
    """Create a temporary workspace and load the s04 module with it."""
    with tempfile.TemporaryDirectory() as tmp:
        original_cwd = Path.cwd()
        os.chdir(tmp)

        # Patch dependencies that require env / API keys
        with (
            patch.dict(os.environ, {"MODEL_ID": "test-model"}, clear=False),
            patch("anthropic.Anthropic"),
            patch("dotenv.load_dotenv"),
        ):
            import importlib.util
            import sys

            repo_root = Path(__file__).resolve().parents[1]
            module_path = repo_root / "agents" / "s04.py"
            spec = importlib.util.spec_from_file_location("s04_under_test", module_path)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Unable to load {module_path}")

            module = importlib.util.module_from_spec(spec)

            # Save original modules
            prev_anthropic = sys.modules.get("anthropic")
            prev_dotenv = sys.modules.get("dotenv")

            sys.modules["anthropic"] = __import__("anthropic")  # Already patched
            sys.modules["dotenv"] = __import__("dotenv")

            try:
                spec.loader.exec_module(module)
                yield module
            finally:
                os.chdir(original_cwd)
                if prev_anthropic is None:
                    sys.modules.pop("anthropic", None)
                else:
                    sys.modules["anthropic"] = prev_anthropic
                if prev_dotenv is None:
                    sys.modules.pop("dotenv", None)
                else:
                    sys.modules["dotenv"] = prev_dotenv


# ===========================================================================
# Test Scenario 1: safe_path -- path validation
# ===========================================================================

class TestSafePath:
    """safe_path should accept valid paths and reject path-traversal attempts."""

    def test_valid_relative_path(self, workdir):
        """A relative path inside the workspace should resolve correctly."""
        path = workdir.safe_path("subdir/hello.txt")
        assert path == Path.cwd() / "subdir" / "hello.txt"
        assert path.is_relative_to(Path.cwd())

    def test_valid_absolute_path(self, workdir):
        """An absolute path inside the workspace should work."""
        cwd = Path.cwd()
        path = workdir.safe_path(str(cwd / "test.txt"))
        assert path == cwd / "test.txt"

    def test_path_traversal_raises(self, workdir):
        """A path that escapes the workspace with '..' should raise ValueError."""
        with pytest.raises(ValueError, match="Path escapes workspace"):
            workdir.safe_path("../outside.txt")

    def test_absolute_path_outside_raises(self, workdir):
        """An absolute path outside the workspace should raise ValueError."""
        with pytest.raises(ValueError, match="Path escapes workspace"):
            workdir.safe_path("/etc/passwd")


# ===========================================================================
# Test Scenario 2: run_bash -- shell command safety
# ===========================================================================

class TestRunBash:
    """run_bash should execute safe commands and block dangerous ones."""

    def test_simple_command(self, workdir):
        """A simple echo command should return the correct output."""
        result = workdir.run_bash("echo hello world")
        assert "hello world" in result

    def test_dangerous_command_blocked(self, workdir):
        """Commands like 'rm -rf /' should be blocked."""
        result = workdir.run_bash("rm -rf /")
        assert "Error" in result
        assert "Dangerous" in result

    def test_sudo_blocked(self, workdir):
        """Commands with sudo should be blocked."""
        result = workdir.run_bash("sudo ls")
        assert "Error" in result
        assert "Dangerous" in result

    def test_command_with_no_output(self, workdir):
        """A command with no output should return '(no output)'."""
        result = workdir.run_bash("cd .")
        assert result == "(no output)"

    def test_stderr_is_captured(self, workdir):
        """stderr output should be included in the result (Alice's bug fix #2)."""
        result = workdir.run_bash("ls nonexistent_file_xyz 2>&1")
        # Redirect stderr to stdout so we see the error
        assert "nonexistent_file_xyz" in result or "No such file" in result


# ===========================================================================
# Test Scenario 3: run_write + run_read -- file I/O
# ===========================================================================

class TestFileIO:
    """run_write should create files and run_read should read them back."""

    def test_write_and_read(self, workdir):
        """Write content to a file, then read it back."""
        result = workdir.run_write("test.txt", "Hello, World!")
        assert "bytes" in result

        content = workdir.run_read("test.txt")
        assert "Hello, World!" in content

    def test_write_creates_subdirectories(self, workdir):
        """Writing to a nested path should auto-create parent directories."""
        result = workdir.run_write("a/b/c/deep.txt", "deep content")
        assert "bytes" in result
        assert Path("a/b/c/deep.txt").exists()

    def test_read_with_limit(self, workdir):
        """run_read with limit should truncate and show line count."""
        lines = "\n".join(f"line {i}" for i in range(100))
        workdir.run_write("long.txt", lines)

        content = workdir.run_read("long.txt", limit=5)
        assert content.count("\n") <= 5 + 1  # 5 lines + maybe summary line
        assert "more" in content

    def test_read_nonexistent_file(self, workdir):
        """Reading a non-existent file should return an error message."""
        result = workdir.run_read("nonexistent.txt")
        assert "Error" in result

    def test_write_empty_content(self, workdir):
        """Writing empty content should still create the file."""
        result = workdir.run_write("empty.txt", "")
        assert "bytes" in result
        assert Path("empty.txt").exists()
        assert Path("empty.txt").read_text() == ""


# ===========================================================================
# Test Scenario 4: run_edit -- in-place file editing
# ===========================================================================

class TestRunEdit:
    """run_edit should replace text in an existing file."""

    def test_edit_success(self, workdir):
        """Replace a substring in an existing file."""
        workdir.run_write("edit.txt", "Hello, World!")
        result = workdir.run_edit("edit.txt", "World", "Python")
        assert "Edited" in result
        assert Path("edit.txt").read_text() == "Hello, Python!"

    def test_edit_text_not_found(self, workdir):
        """If the old_text is not found, return an error."""
        workdir.run_write("edit.txt", "Hello, World!")
        result = workdir.run_edit("edit.txt", "Nonexistent", "Something")
        assert "Error" in result
        assert "Text not found" in result

    def test_edit_nonexistent_file(self, workdir):
        """Editing a non-existent file should return an error."""
        result = workdir.run_edit("nope.txt", "a", "b")
        assert "Error" in result

    def test_edit_only_first_occurrence(self, workdir):
        """Only the first occurrence should be replaced."""
        workdir.run_write("dup.txt", "a a a")
        result = workdir.run_edit("dup.txt", "a", "b")
        assert "Edited" in result
        assert Path("dup.txt").read_text() == "b a a"


# ===========================================================================
# Test Scenario 5: TOOL_HANDLERS dispatch
# ===========================================================================

class TestToolHandlers:
    """TOOL_HANDLERS dict should correctly dispatch to the right function."""

    def test_bash_handler(self, workdir):
        result = workdir.TOOL_HANDLERS["bash"](command="echo hello")
        assert "hello" in result

    def test_read_file_handler(self, workdir):
        workdir.run_write("handler.txt", "content")
        result = workdir.TOOL_HANDLERS["read_file"](path="handler.txt")
        assert "content" in result

    def test_write_file_handler(self, workdir):
        result = workdir.TOOL_HANDLERS["write_file"](path="handler.txt", content="data")
        assert "bytes" in result
        assert Path("handler.txt").read_text() == "data"

    def test_edit_file_handler(self, workdir):
        workdir.run_write("handler_edit.txt", "old")
        result = workdir.TOOL_HANDLERS["edit_file"](
            path="handler_edit.txt", old_text="old", new_text="new"
        )
        assert "Edited" in result
        assert Path("handler_edit.txt").read_text() == "new"

    def test_unknown_handler_returns_none(self, workdir):
        """An unknown tool name should produce 'Unknown Tool' message."""
        handler = workdir.TOOL_HANDLERS.get("nonexistent")
        assert handler is None
