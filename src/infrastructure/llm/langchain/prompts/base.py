"""Base prompt management system with version control."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from langchain.prompts import PromptTemplate
from pydantic import BaseModel, Field


class PromptVersion(BaseModel):
    """Prompt version information."""

    version: str = Field(..., description="版本号 (e.g., '1.0.0')")
    created_at: datetime = Field(default_factory=datetime.now)
    description: str = Field(..., description="版本描述")
    is_active: bool = Field(default=True, description="是否为活跃版本")


class BasePrompt(ABC):
    """Base class for all prompt templates."""

    def __init__(self, version: str = "1.0.0", description: str = ""):
        """Initialize base prompt.

        Args:
            version: Version string for the prompt.
            description: Description of this prompt version.
        """
        self.version_info = PromptVersion(version=version, description=description)
        self._template = self._create_template()

    @abstractmethod
    def _create_template(self) -> str:
        """Create the prompt template string.

        Returns:
            The prompt template string with variable placeholders.
        """
        pass

    @abstractmethod
    def get_input_variables(self) -> list[str]:
        """Get required input variables for this prompt.

        Returns:
            List of required input variable names.
        """
        pass

    def get_prompt_template(self) -> PromptTemplate:
        """Get LangChain PromptTemplate instance.

        Returns:
            Configured PromptTemplate instance.
        """
        return PromptTemplate(
            template=self._template, input_variables=self.get_input_variables()
        )

    def format(self, **kwargs: Any) -> str:
        """Format the prompt with provided variables.

        Args:
            **kwargs: Variables to format the prompt with.

        Returns:
            Formatted prompt string.
        """
        prompt = self.get_prompt_template()
        return prompt.format(**kwargs)

    def get_version(self) -> str:
        """Get the version of this prompt.

        Returns:
            Version string.
        """
        return self.version_info.version

    def get_metadata(self) -> dict[str, Any]:
        """Get metadata about this prompt.

        Returns:
            Dictionary containing prompt metadata.
        """
        return {
            "version": self.version_info.version,
            "created_at": self.version_info.created_at.isoformat(),
            "description": self.version_info.description,
            "is_active": self.version_info.is_active,
            "input_variables": self.get_input_variables(),
        }


class PromptManager:
    """Manages different prompt versions and types."""

    def __init__(self):
        """Initialize prompt manager."""
        self._prompts: dict[str, dict[str, BasePrompt]] = {}

    def register_prompt(
        self, prompt_type: str, prompt: BasePrompt, set_as_active: bool = True
    ) -> None:
        """Register a prompt with the manager.

        Args:
            prompt_type: Type of prompt (e.g., 'annual_report', 'research_report').
            prompt: The prompt instance to register.
            set_as_active: Whether to set this as the active version.
        """
        if prompt_type not in self._prompts:
            self._prompts[prompt_type] = {}

        version = prompt.get_version()

        # Deactivate other versions if setting as active
        if set_as_active:
            for existing_prompt in self._prompts[prompt_type].values():
                existing_prompt.version_info.is_active = False

        self._prompts[prompt_type][version] = prompt

    def get_prompt(self, prompt_type: str, version: str | None = None) -> BasePrompt:
        """Get a prompt by type and version.

        Args:
            prompt_type: Type of prompt to retrieve.
            version: Specific version to get. If None, returns active version.

        Returns:
            The requested prompt.

        Raises:
            ValueError: If prompt type or version not found.
        """
        if prompt_type not in self._prompts:
            raise ValueError(f"Prompt type '{prompt_type}' not found")

        if version:
            if version not in self._prompts[prompt_type]:
                raise ValueError(
                    f"Version '{version}' not found for prompt type '{prompt_type}'"
                )
            return self._prompts[prompt_type][version]

        # Find active version
        for prompt in self._prompts[prompt_type].values():
            if prompt.version_info.is_active:
                return prompt

        raise ValueError(f"No active version found for prompt type '{prompt_type}'")
