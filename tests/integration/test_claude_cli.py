"""Testes do adapter do Claude CLI contra saída gravada de subprocesso (sem rede)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from notion_copilot.adapters import claude_cli
from notion_copilot.adapters.claude_cli import ClaudeCliRunner, check_problems
from notion_copilot.adapters.logging_fs import EventLog

STREAM = "\n".join(
    [
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "assistant", "message": {"content": []}}),
        json.dumps(
            {"type": "result", "subtype": "success", "result": '{"title": "ok"}'}
        ),
    ]
)


def make_runner(tmp_path) -> ClaudeCliRunner:
    return ClaudeCliRunner(
        model="glm-5.3",
        base_url="https://api.z.ai/api/anthropic",
        auth_token="tok-123",
        mcp_config_path=Path("/abs/.mcp.json"),
        timeout_s=600.0,
        max_turns=20,
        events=EventLog(state_dir=tmp_path),
    )


def capture_run(monkeypatch, *, stdout=STREAM, returncode=0):
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        if returncode != 0:
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 600))
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(claude_cli.subprocess, "run", fake_run)
    return captured


def test_passes_only_the_web_tools_in_the_allowlist_with_absolute_mcp_config(
    tmp_path, monkeypatch
):
    captured = capture_run(monkeypatch)
    runner = make_runner(tmp_path)

    runner.run_refine("prompt do refinamento", run_id="r1", card_id="card-1")

    cmd = captured["cmd"]
    assert cmd[0] == "claude"
    assert cmd[cmd.index("-p") + 1] == "prompt do refinamento"
    i = cmd.index("--allowedTools")
    assert cmd[i + 1 : i + 3] == ["mcp__web_search_prime", "mcp__web_reader"]
    assert "notion" not in " ".join(cmd)
    j = cmd.index("--mcp-config")
    assert cmd[j + 1] == "/abs/.mcp.json"
    assert cmd[cmd.index("--model") + 1] == "glm-5.3"
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"


def test_sends_credentials_only_to_the_subprocess_environment(tmp_path, monkeypatch):
    captured = capture_run(monkeypatch)
    monkeypatch.setenv("NC_SENTINEL_PARENT_VAR", "nao-vazar")
    runner = make_runner(tmp_path)

    runner.run_refine("prompt", run_id="r1", card_id="card-1")

    env = captured["kwargs"]["env"]
    assert env["ANTHROPIC_AUTH_TOKEN"] == "tok-123"
    assert env["ANTHROPIC_BASE_URL"] == "https://api.z.ai/api/anthropic"
    assert "NC_SENTINEL_PARENT_VAR" not in env
    assert "PATH" in env and "HOME" in env


def test_parses_the_final_result_from_the_stream_json_output(tmp_path, monkeypatch):
    capture_run(monkeypatch)
    runner = make_runner(tmp_path)

    result = runner.run_refine("prompt", run_id="r1", card_id="card-1")

    assert result == '{"title": "ok"}'
    trail = tmp_path / "trails" / "r1" / "card-1.jsonl"
    assert trail.is_file()
    assert trail.read_text() == STREAM


def test_stops_the_agent_at_the_configured_timeout(tmp_path, monkeypatch):
    captured = capture_run(monkeypatch, returncode=124)
    runner = make_runner(tmp_path)

    with pytest.raises(TimeoutError):
        runner.run_refine("prompt", run_id="r1", card_id="card-1")

    assert captured["kwargs"]["timeout"] == 600.0


def test_check_problems_reports_a_missing_claude_executable(monkeypatch):
    monkeypatch.setattr(claude_cli.shutil, "which", lambda name: None)

    problems = check_problems()

    assert problems and "claude" in problems[0]
