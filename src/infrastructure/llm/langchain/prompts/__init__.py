"""Prompt templates for LLM extraction."""

from .annual_report import AnnualReportPromptV1
from .base import BasePrompt, PromptManager
from .research_report import ResearchReportPromptV1

# Global prompt manager instance
_prompt_manager = PromptManager()

# Register default prompts
_prompt_manager.register_prompt("annual_report", AnnualReportPromptV1())
_prompt_manager.register_prompt("research_report", ResearchReportPromptV1())


def get_prompt_manager() -> PromptManager:
    """Get the global prompt manager instance.

    Returns:
        The global PromptManager instance.
    """
    return _prompt_manager


def get_prompt(prompt_type: str, version: str | None = None) -> BasePrompt:
    """Get a prompt by type and optional version.

    Args:
        prompt_type: Type of prompt ('annual_report' or 'research_report').
        version: Optional specific version. If None, returns active version.

    Returns:
        The requested prompt template.
    """
    return _prompt_manager.get_prompt(prompt_type, version)


__all__ = [
    "BasePrompt",
    "PromptManager",
    "AnnualReportPromptV1",
    "ResearchReportPromptV1",
    "get_prompt_manager",
    "get_prompt",
]
