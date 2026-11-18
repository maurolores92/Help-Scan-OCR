import os
import logging
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware

try:
    from app.models.schemas import ExtractionResponse, ExtractionRequest
    from app.extractors.hybrid_engine import extract_text_and_pages
    from app.extractors.document_classifier import classify_and_extract_metadata
except (ImportError, ValueError):
    from models.schemas import ExtractionResponse, ExtractionRequest
    from extractors.hybrid_engine import extract_text_and_pages
    from extractors.document_classifier import classify_and_extract_metadata

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("hc_scan_ocr")

app = FastAPI(
    title="HC-Scan OCR Microservice",
    description="Microservicio de OCR y Extracción Documental de Alto Rendimiento para HelpCopies ERP",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "hc-scan-ocr",
        "version": "1.0.0",
    }


@app.post("/extract", response_model=ExtractionResponse)
async def extract_document(
    file: Optional[UploadFile] = File(None),
    file_path: Optional[str] = Form(None),
    original_name: Optional[str] = Form(None),
    body: Optional[ExtractionRequest] = Body(None),
):
    """
    Extrae texto y datos estructurados de un documento PDF.
    Acepta el archivo por:
    1. HTTP Multipart (subida directa de binario en `file`)
    2. Ruta compartida en disco (`file_path` por formulario o por body JSON)
    """
    pdf_bytes: Optional[bytes] = None
    file_name = original_name or "documento.pdf"

    # Caso 1: Envió archivo binario multipart
    if file is not None:
        file_name = file.filename or file_name
        pdf_bytes = await file.read()
    # Caso 2: Envió ruta por form-data o body JSON
    else:
        target_path = file_path or (body.file_path if body else None)
        if body and body.original_name:
            file_name = body.original_name

        if not target_path:
            raise HTTPException(
                status_code=400,
                detail="Se debe proporcionar un archivo en 'file' o una ruta en 'file_path'",
            )

        if not os.path.isfile(target_path):
            raise HTTPException(
                status_code=404,
                detail=f"El archivo especificado no existe en el sistema de archivos: {target_path}",
            )

        try:
            with open(target_path, "rb") as f:
                pdf_bytes = f.read()
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"No se pudo leer el archivo en disco ({target_path}): {str(e)}",
            )

    if not pdf_bytes or len(pdf_bytes) < 5:
        raise HTTPException(status_code=400, detail="El archivo PDF está vacío o corrupto")

    logger.info(f"Iniciando extracción OCR para '{file_name}' ({len(pdf_bytes)} bytes)...")

    try:
        raw_text, page_count, engine = extract_text_and_pages(pdf_bytes)
        logger.info(
            f"Extracción finalizada para '{file_name}': {page_count} páginas, "
            f"motor={engine}, caracteres={len(raw_text)}"
        )

        result = classify_and_extract_metadata(
            raw_text=raw_text,
            original_file_name=file_name,
            page_count=page_count,
            engine=engine,
        )
        return result
    except Exception as e:
        logger.error(f"Error procesando '{file_name}': {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Fallo en motor de extracción: {str(e)}")
