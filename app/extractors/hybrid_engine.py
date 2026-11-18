import io
import logging
from typing import Tuple

logger = logging.getLogger("ocr_service.hybrid_engine")

# Verificar disponibilidad de librerías
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF (fitz) no está disponible en este entorno.")

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract o Pillow no están disponibles en este entorno.")


def extract_text_and_pages(pdf_bytes: bytes) -> Tuple[str, int, str]:
    """
    Motor híbrido de doble capa:
    1. PyMuPDF (fitz) extrae el flujo de texto nativo digital (Tango ERP, AFIP, Word) en 10-30ms.
    2. Si el PDF es un escaneo de imagen raster (ej. escaneo directo desde HP LaserJet sin capa de texto),
       renderiza las páginas a 200 DPI y ejecuta OCR con Tesseract en español.
    """
    if not PYMUPDF_AVAILABLE:
        raise RuntimeError("PyMuPDF no está instalado para procesar archivos PDF.")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    combined_pages_text = []
    has_meaningful_native_text = False
    used_engine = "python_pymupdf_native"

    for page_idx in range(page_count):
        page = doc[page_idx]
        text = page.get_text("text") or ""
        clean_text = text.strip()

        # Si la página tiene texto embebido significativo (más de 30 caracteres alfanuméricos)
        if len(clean_text) >= 30:
            combined_pages_text.append(clean_text)
            has_meaningful_native_text = True
        else:
            # Página vacía o es una imagen raster escaneada
            if TESSERACT_AVAILABLE:
                try:
                    logger.info(f"Página {page_idx + 1}/{page_count} sin texto nativo. Ejecutando OCR Tesseract (spa+eng)...")
                    # Render a 200 DPI para balance óptimo entre velocidad y precisión
                    pix = page.get_pixmap(dpi=200)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    ocr_text = pytesseract.image_to_string(img, lang="spa+eng", config="--psm 3")
                    combined_pages_text.append(ocr_text.strip())
                    used_engine = "python_tesseract_ocr"
                except Exception as ocr_err:
                    logger.warning(f"No se pudo ejecutar OCR en página {page_idx + 1}: {ocr_err}")
                    combined_pages_text.append(clean_text)
            else:
                combined_pages_text.append(clean_text)

    doc.close()
    full_text = "\n\n".join(t for t in combined_pages_text if t)
    return full_text, page_count, used_engine
