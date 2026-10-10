"""Testes da tabela de etapas (constituição IX e III)."""

from notion_copilot.domain.stages import STAGES


def test_the_refine_stage_declares_prompts_refine_md_and_only_the_web_tools():
    refine = STAGES["refine"]

    assert refine.prompt_file == "refine.md"
    assert set(refine.allowed_tools) == {
        "mcp__web_search_prime",
        "mcp__web_reader",
    }
    assert all("notion" not in tool for tool in refine.allowed_tools)
