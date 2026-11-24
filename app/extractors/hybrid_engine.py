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
    from PIL import Image, ImageOps
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract o Pillow no están disponibles en este entorno.")


def preprocess_image_for_ocr(img: Image.Image) -> Image.Image:
    """
    Mejora la calidad de la imagen escaneada para maximizar la tasa de acierto de Tesseract:
    1. Conversión a escala de grises.
    2. Autocontraste suave: atenúa el fondo del papel sin borrar trazos finos de lapicera.
    """
    try:
        gray = img.convert("L")
        enhanced = ImageOps.autocontrast(gray, cutoff=1)
        return enhanced
    except Exception:
        return img


def extract_text_and_pages(pdf_bytes: bytes) -> Tuple[str, int, str]:
    """
    Motor híbrido de doble capa:
    1. PyMuPDF (fitz) extrae el flujo de texto nativo digital (Tango ERP, AFIP, Word) en 10-30ms.
    2. Si alguna página no tiene capa de texto digital suficiente (escaneo, foto o manuscrito),
       marca el motor como `python_tesseract_ocr` para que el backend pueda combinar OCR + Gemini Vision,
       renderiza la página a 300 DPI y ejecuta Tesseract en español.
    """
    if not PYMUPDF_AVAILABLE:
        raise RuntimeError("PyMuPDF no está instalado para procesar archivos PDF.")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    combined_pages_text = []
    has_raster_page = False

    for page_idx in range(page_count):
        page = doc[page_idx]
        text = page.get_text("text") or ""
        clean_text = text.strip()
        alnum_chars = sum(1 for ch in clean_text if ch.isalnum())

        # Si la página tiene texto nativo digital significativo (>= 50 caracteres alfanuméricos)
        if alnum_chars >= 50:
            combined_pages_text.append(clean_text)
        else:
            has_raster_page = True
            # Página vacía o imagen raster escaneada / foto de remito o factura
            if TESSERACT_AVAILABLE:
                try:
                    logger.info(f"Página {page_idx + 1}/{page_count} sin texto nativo. Renderizando a 300 DPI y ejecutando OCR Tesseract...")
                    # Render a 300 DPI para óptima nitidez de letras y números
                    pix = page.get_pixmap(dpi=300)
                    raw_img = Image.open(io.BytesIO(pix.tobytes("png")))
                    processed_img = preprocess_image_for_ocr(raw_img)

                    # Intento 1: Segmentación automática estándar con modelo neuronal LSTM
                    ocr_text = pytesseract.image_to_string(
                        processed_img,
                        lang="spa+eng",
                        config="--oem 1 --psm 3",
                    ).strip()

                    # Fallback si extrajo muy pocos caracteres (ej. tablas o bloques densos)
                    if len(ocr_text) < 25:
                        fallback_text = pytesseract.image_to_string(
                            processed_img,
                            lang="spa+eng",
                            config="--oem 1 --psm 6",
                        ).strip()
                        if len(fallback_text) > len(ocr_text):
                            ocr_text = fallback_text

                    combined_pages_text.append(ocr_text)
                    logger.info(
                        f"Página {page_idx + 1} procesada por OCR con éxito: {len(ocr_text)} caracteres detectados"
                    )
                except Exception as ocr_err:
                    logger.warning(f"No se pudo ejecutar OCR en página {page_idx + 1}: {ocr_err}")
                    combined_pages_text.append(clean_text)
            else:
                combined_pages_text.append(clean_text)

    doc.close()
    used_engine = "python_tesseract_ocr" if has_raster_page else "python_pymupdf_native"
    full_text = "\n\n".join(t for t in combined_pages_text if t)
    return full_text, page_count, used_engine
