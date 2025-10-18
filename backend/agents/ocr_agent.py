import io
from typing import Dict, Any
import pytesseract
from PIL import Image
import fitz  # PyMuPDF

async def run_ocr(doc: Dict[str, Any], lang="por"):
    if doc["kind"] == "PDF":
        text = ""
        pdf = fitz.open(stream=doc["raw"], filetype="pdf")
        for page in pdf:
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text += pytesseract.image_to_string(img, lang=lang) + "\n"
        return {"text": text}
    elif doc["kind"] == "IMAGE":
        img = Image.open(io.BytesIO(doc["raw"]))
        text = pytesseract.image_to_string(img, lang=lang)
        return {"text": text}
    return {}
