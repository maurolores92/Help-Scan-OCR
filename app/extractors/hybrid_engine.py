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
    2. Autocontraste dinámico: elimina velo grisáceo de fondo del papel y resalta caracteres oscuros.
    """
    try:
        gray = img.convert("L")
        enhanced = ImageOps.autocontrast(gray, cutoff=2)
        return enhanced
    except Exception:
        return img


def extract_text_and_pages(pdf_bytes: bytes) -> Tuple[str, int, str]:
    """
    Motor híbrido de doble capa:
    1. PyMuPDF (fitz) extrae el flujo de texto nativo digital (Tango ERP, AFIP, Word) en 10-30ms.
    2. Si el PDF es un escaneo de imagen raster (ej. escaneo directo desde HP LaserJet sin capa de texto),
       renderiza las páginas a 300 DPI, aplica preprocesamiento de contraste y ejecuta OCR con Tesseract en español.
    """
    if not PYMUPDF_AVAILABLE:
        raise RuntimeError("PyMuPDF no está instalado para procesar archivos PDF.")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = len(doc)
    combined_pages_text = []
    used_engine = "python_pymupdf_native"

    for page_idx in range(page_count):
        page = doc[page_idx]
        text = page.get_text("text") or ""
        clean_text = text.strip()

        # Si la página tiene texto embebido significativo (más de 30 caracteres alfanuméricos)
        if len(clean_text) >= 30:
            combined_pages_text.append(clean_text)
        else:
            # Página vacía o es una imagen raster escaneada desde impresora
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
                    used_engine = "python_tesseract_ocr"
                    logger.info(
                        f"Página {page_idx + 1} procesada por OCR con éxito: {len(ocr_text)} caracteres detectados"
                    )
                except Exception as ocr_err:
                    logger.warning(f"No se pudo ejecutar OCR en página {page_idx + 1}: {ocr_err}")
                    combined_pages_text.append(clean_text)
            else:
                combined_pages_text.append(clean_text)

    doc.close()
    full_text = "\n\n".join(t for t in combined_pages_text if t)
    return full_text, page_count, used_engine
