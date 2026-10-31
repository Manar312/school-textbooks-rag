from typing import AsyncIterator

import anthropic

from app.core.errors import ConfigError
from app.providers.base import LLMProvider, LLMResult, StreamChunk


class AnthropicLLM(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        if not api_key:
            raise ConfigError("Anthropic provider needs ANTHROPIC_API_KEY (or the role's *_API_KEY)")
        self.model = model
        self.client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url, max_retries=3, timeout=120)

    async def complete(self, *, system: str, messages: list[dict], max_tokens: int = 1024) -> LLMResult:
        msg = await self.client.messages.create(model=self.model, max_tokens=max_tokens, system=system,
                                                messages=messages)
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        return LLMResult(text, msg.usage.input_tokens, msg.usage.output_tokens, msg.stop_reason == "max_tokens")

    async def stream(self, *, system: str, messages: list[dict], max_tokens: int = 1800) -> AsyncIterator[StreamChunk]:
        async with self.client.messages.stream(model=self.model, max_tokens=max_tokens, system=system,
                                               messages=messages) as s:
            async for t in s.text_stream:
                yield StreamChunk(text=t)
            final = await s.get_final_message()
            yield StreamChunk(tokens_in=final.usage.input_tokens, tokens_out=final.usage.output_tokens)

    async def aclose(self) -> None:
        await self.client.close()
