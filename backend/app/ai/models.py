"""Model provider adapter.

Graph nodes depend on the small `ResearchModel` interface, not on a vendor SDK:

* `LangChainResearchModel` wraps any LangChain chat model. Swapping OpenAI for another provider
  is a change to `build_research_model` (e.g. `init_chat_model(..., model_provider="anthropic")`).
* `MockResearchModel` (app.ai.mock) is deterministic and offline, for tests and demo mode.

`context` carries the raw (unrendered) inputs. Real models ignore it and read the rendered
prompt; the mock uses it because it cannot read prose.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolCall
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from app.core.config import Settings
from app.core.retry import call_with_retries


class ResearchModel(ABC):
    name: str

    @abstractmethod
    async def structured[T: BaseModel](
        self,
        schema: type[T],
        prompt: ChatPromptTemplate,
        inputs: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
    ) -> T:
        """Run the prompt and return output validated against `schema`."""

    @abstractmethod
    async def tool_calls(
        self,
        prompt: ChatPromptTemplate,
        inputs: dict[str, Any],
        tools: Sequence[type[BaseModel]],
        *,
        context: dict[str, Any] | None = None,
    ) -> list[ToolCall]:
        """Let the model choose tool calls (name + args). The caller executes them."""


class LangChainResearchModel(ResearchModel):
    def __init__(self, chat_model: BaseChatModel, *, timeout: float, name: str):
        self.chat_model = chat_model
        self.timeout = timeout
        self.name = name

    async def structured[T: BaseModel](
        self,
        schema: type[T],
        prompt: ChatPromptTemplate,
        inputs: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
    ) -> T:
        # function_calling works across providers and tolerates optional fields in schemas.
        chain = prompt | self.chat_model.with_structured_output(schema, method="function_calling")
        # The SDK already retries rate limits / 5xx; we only add an overall timeout here.
        result = await call_with_retries(
            lambda: chain.ainvoke(inputs),
            what=f"LLM {schema.__name__}",
            timeout=self.timeout,
            retries=0,
        )
        if not isinstance(result, schema):  # defensive: some providers return dicts
            result = schema.model_validate(result)
        return result

    async def tool_calls(
        self,
        prompt: ChatPromptTemplate,
        inputs: dict[str, Any],
        tools: Sequence[type[BaseModel]],
        *,
        context: dict[str, Any] | None = None,
    ) -> list[ToolCall]:
        chain = prompt | self.chat_model.bind_tools(list(tools))
        message = await call_with_retries(
            lambda: chain.ainvoke(inputs),
            what="LLM tool selection",
            timeout=self.timeout,
            retries=0,
        )
        return list(getattr(message, "tool_calls", []) or [])


def build_research_model(settings: Settings) -> ResearchModel:
    if settings.llm_provider == "openai":
        from langchain.chat_models import init_chat_model

        kwargs: dict[str, Any] = {
            "api_key": settings.openai_api_key,
            "timeout": settings.llm_timeout_seconds,
            "max_retries": settings.external_max_retries,
        }
        if settings.llm_temperature is not None:
            kwargs["temperature"] = settings.llm_temperature
        chat_model = init_chat_model(settings.llm_model, model_provider="openai", **kwargs)
        return LangChainResearchModel(
            chat_model,
            timeout=settings.llm_timeout_seconds * 2,
            name=f"openai:{settings.llm_model}",
        )

    from app.ai.mock import MockResearchModel

    return MockResearchModel()
