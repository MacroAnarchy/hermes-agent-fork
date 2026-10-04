"""In-process kanban tool calls must resolve the board from the ACTIVE PROFILE's
pin (profile .env HERMES_KANBAN_BOARD), not only the gateway process env / global
``current`` symlink. A multiplex gateway serves every profile in one process; the
profile pin exists precisely for per-team boards and never reaches os.environ."""
import os
from pathlib import Path

import pytest


def test_profile_env_pin_wins_for_in_process_calls(tmp_path, monkeypatch):
    from hermes_cli import kanban_db as kbd
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override

    home = tmp_path / "home"
    (home / "kanban" / "boards" / "board-a").mkdir(parents=True)
    (home / "kanban" / "boards" / "board-a" / "kanban.db").write_bytes(b"")
    (home / "kanban" / "boards" / "board-b").mkdir(parents=True)
    (home / "kanban" / "boards" / "board-b" / "kanban.db").write_bytes(b"")
    monkeypatch.setenv("HERMES_HOME", str(home))
    token = set_hermes_home_override(home)
    try:
        # Global default points at board-b (e.g. a `boards switch` months ago)
        (home / "kanban" / "current").write_text("board-b\n")
        monkeypatch.delenv("HERMES_KANBAN_BOARD", raising=False)
        monkeypatch.delenv("HERMES_KANBAN_HOME", raising=False)
        assert kbd.get_current_board() == "board-b"

        # The profile's pin lives in profiles/<name>/.env — the same place the CLI
        # child loads it from. An in-process call made while THAT profile is active
        # (multiplex gateway) must resolve to the profile's board, not the global.
        prof = home / "profiles" / "worker-a"
        prof.mkdir(parents=True)
        (prof / ".env").write_text("HERMES_KANBAN_BOARD=board-a\n")

        # Simulate the multiplex gateway serving this profile: the session ContextVar
        # names the active profile; the pin must win over the global `current`.
        from gateway.session_context import set_session_vars, clear_session_vars
        tokens = set_session_vars(platform="api_server", chat_id="20260104_x", profile="worker-a")
        try:
            assert kbd.get_current_board() == "board-a", (
                "profile .env pin must win for in-process calls under multiplex")
        finally:
            clear_session_vars(tokens)
    finally:
        reset_hermes_home_override(token)
