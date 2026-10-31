import base64

import anthropic

from app.core.errors import ConfigError
from app.providers.base import LLMResult, VLMProvider


class AnthropicVLM(VLMProvider):
    name = "anthropic"

    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        if not api_key:
            raise ConfigError("Anthropic provider needs ANTHROPIC_API_KEY (or VLM_API_KEY)")
        self.model = model
        self.client = anthropic.AsyncAnthropic(api_key=api_key, base_url=base_url, max_retries=5, timeout=180)

    async def read_image(self, *, image: bytes, mime: str, system: str, instruction: str,
                         max_tokens: int) -> LLMResult:
        msg = await self.client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime,
                                             "data": base64.b64encode(image).decode()}},
                {"type": "text", "text": instruction}]}])
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        return LLMResult(text, msg.usage.input_tokens, msg.usage.output_tokens, msg.stop_reason == "max_tokens")

    async def aclose(self) -> None:
        await self.client.close()
