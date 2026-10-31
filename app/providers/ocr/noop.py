from app.providers.base import OCRProvider


class NoopOCR(OCRProvider):
    name = "none"

    def __init__(self, languages: str | None = None):
        pass

    async def read(self, image_png: bytes) -> str:
        return ""
