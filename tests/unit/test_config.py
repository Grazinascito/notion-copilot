"""Testes da configuração (.env, permissões, diretórios — research R3/R4)."""

from notion_copilot.config import Settings, env_file_problem


def test_rejects_an_env_file_with_permissions_looser_than_600(tmp_path):
    loose = tmp_path / "loose.env"
    loose.write_text("NOTION_TOKEN=x\n")
    loose.chmod(0o644)

    problem = env_file_problem(loose)

    assert problem is not None
    assert "chmod 600" in problem

    tight = tmp_path / "tight.env"
    tight.write_text("NOTION_TOKEN=x\n")
    tight.chmod(0o600)

    assert env_file_problem(tight) is None


def test_resolves_the_state_dir_via_platformdirs_and_exposes_absolute_paths(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prompts").mkdir()
    settings = Settings(
        _env_file=None,
        state_dir=tmp_path / "state",
    )

    assert settings.resolved_state_dir.is_absolute()
    assert settings.resolved_state_dir == (tmp_path / "state").resolve()

    assert settings.mcp_config_path.is_absolute()
    assert settings.mcp_config_path.name == ".mcp.json"
    assert settings.mcp_config_path.parent == tmp_path.resolve()

    assert settings.prompts_dir.is_absolute()
    assert settings.prompts_dir.name == "prompts"
    assert settings.prompts_dir.parent == tmp_path.resolve()
