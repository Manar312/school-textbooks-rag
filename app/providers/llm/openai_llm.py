from typing import AsyncIterator

from openai import AsyncOpenAI

from app.providers.base import LLMProvider, LLMResult, StreamChunk


def token_limit_kwargs(base_url: str | None, max_tokens: int) -> dict:
    # api.openai.com expects max_completion_tokens; OpenAI-compatible servers (vLLM, Ollama, OpenRouter...) max_tokens
    return {"max_completion_tokens": max_tokens} if base_url is None else {"max_tokens": max_tokens}


class OpenAILLM(LLMProvider):
    """OpenAI, or ANY OpenAI-compatible server (vLLM, Ollama, LM Studio, OpenRouter, Gemini/DeepSeek compat...) via LLM_BASE_URL."""
    name = "openai"

    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        self.model = model
        self.base_url = base_url
        self.client = AsyncOpenAI(api_key=api_key or "not-needed", base_url=base_url, max_retries=3, timeout=120)

    def _msgs(self, system: str, messages: list[dict]) -> list[dict]:
        return [{"role": "system", "content": system}, *messages]

    async def complete(self, *, system: str, messages: list[dict], max_tokens: int = 1024) -> LLMResult:
        r = await self.client.chat.completions.create(model=self.model, messages=self._msgs(system, messages),
                                                      **token_limit_kwargs(self.base_url, max_tokens))
        ch = r.choices[0]
        u = r.usage
        return LLMResult((ch.message.content or "").strip(), u.prompt_tokens if u else 0,
                         u.completion_tokens if u else 0, ch.finish_reason == "length")

    async def stream(self, *, system: str, messages: list[dict], max_tokens: int = 1800) -> AsyncIterator[StreamChunk]:
        stream = await self.client.chat.completions.create(
            model=self.model, messages=self._msgs(system, messages), stream=True,
            stream_options={"include_usage": True}, **token_limit_kwargs(self.base_url, max_tokens))
        tin = tout = None
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield StreamChunk(text=chunk.choices[0].delta.content)
            if getattr(chunk, "usage", None):
                tin, tout = chunk.usage.prompt_tokens, chunk.usage.completion_tokens
        yield StreamChunk(tokens_in=tin or 0, tokens_out=tout or 0)

    async def aclose(self) -> None:
        await self.client.close()
