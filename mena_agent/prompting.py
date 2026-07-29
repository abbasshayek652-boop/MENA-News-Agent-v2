"""Builds the LLM prompt context from ranked, extracted articles."""

from __future__ import annotations

from pathlib import Path

PROMPT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "orchestrator.md"


def load_prompt_template() -> str:
    return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")


def build_context(items: list[dict], max_items: int = 25, snippet_chars: int = 1200) -> str:
    """Render ranked items into a compact text block the LLM can reason over."""
    blocks = []
    for i, item in enumerate(items[:max_items], start=1):
        title = item.get("title", "Untitled")
        source = item.get("source_name", "Unknown source")
        tier = item.get("tier", "C")
        url = item.get("url", "")
        snippet = (item.get("snippet", "") or "")[:snippet_chars]
        blocks.append(
            f"[{i}] ({tier}-tier | {source})\nTitle: {title}\nURL: {url}\nExcerpt: {snippet}\n"
        )
    return "\n---\n".join(blocks)


def build_prompts(items: list[dict]) -> tuple[str, str]:
    """Returns (system_prompt, user_prompt) for the LLM call."""
    template = load_prompt_template()
    context = build_context(items)

    # The template's own "Role/Lens/Task/Output Requirements/Constraints"
    # sections act as the system prompt; the rendered context is the user
    # turn's content to analyze.
    system_prompt, _, _ = template.partition("## Input Context")
    user_prompt = context
    return system_prompt.strip(), user_prompt
