import asyncio
import io

from app.providers.base import OCRProvider


class TesseractOCR(OCRProvider):
    name = "tesseract"

    def __init__(self, languages: str = "ara+eng+fra"):
        self.languages = languages

    def _run(self, png: bytes) -> str:
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.open(io.BytesIO(png)), lang=self.languages)

    async def read(self, image_png: bytes) -> str:
        return await asyncio.to_thread(self._run, image_png)
