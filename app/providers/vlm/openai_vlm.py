import base64

from openai import AsyncOpenAI

from app.providers.base import LLMResult, VLMProvider
from app.providers.llm.openai_llm import token_limit_kwargs


class OpenAIVLM(VLMProvider):
    """Any OpenAI-compatible vision model (GPT-4o family, Qwen2.5-VL / InternVL served by vLLM, Gemini compat...)."""
    name = "openai"

    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        self.model = model
        self.base_url = base_url
        self.client = AsyncOpenAI(api_key=api_key or "not-needed", base_url=base_url, max_retries=5, timeout=180)

    async def read_image(self, *, image: bytes, mime: str, system: str, instruction: str,
                         max_tokens: int) -> LLMResult:
        url = f"data:{mime};base64,{base64.b64encode(image).decode()}"
        r = await self.client.chat.completions.create(
            model=self.model, **token_limit_kwargs(self.base_url, max_tokens),
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": [{"type": "text", "text": instruction},
                                                   {"type": "image_url", "image_url": {"url": url}}]}])
        ch, u = r.choices[0], r.usage
        return LLMResult((ch.message.content or "").strip(), u.prompt_tokens if u else 0,
                         u.completion_tokens if u else 0, ch.finish_reason == "length")

    async def aclose(self) -> None:
        await self.client.close()
