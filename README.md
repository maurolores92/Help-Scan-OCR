# HC-Scan OCR Microservice (Python FastAPI)

Microservicio de OCR y análisis semántico para el backend de HelpCopies ERP (`HC-Scan`).

## Características
1. **Doble Motor Híbrido**:
   - **PyMuPDF (`fitz`)**: Extracción nativa digital ultrarrápida (10-30 ms) para documentos generados por sistemas contables (Tango ERP, AFIP, Word a PDF).
   - **Tesseract OCR (spa + eng)**: Renderizado a 200 DPI y reconocimiento óptico de caracteres para escaneos rasterizados directamente desde impresoras y multifuncionales HP (LaserJet Managed E52645, etc.) o Ricoh sin capa de texto embebida.
2. **Extracción Completa de Ítems / Artículos**:
   - Detección de líneas de factura compactas de ERP AFIP.
   - Detección de presupuestos y notas de pedido con código prefijo (`HC 1 - M320F`).
   - Detección de partes técnicas y repuestos con viñetas (` UNI FOTOCONDUCTORA MP 201-1515 (1)`).
   - Detección de tablas multi-industria con columnas de código, descripción, cantidad y precio.
3. **Extracción de Metadatos Administrativos**:
   - CUIT (Emisor y Cliente), CAE AFIP de 14 dígitos, fechas, totales, subtotal, IVA, equipo ID, contadores (`ACT:8 - ANT:7`).
4. **Modos de Ingesta**:
   - `POST /extract` con archivo binario `multipart/form-data` (aislamiento por red HTTP).
   - `POST /extract` con ruta en disco compartido `file_path` (máxima velocidad en Docker con volumen compartido).

## Ejecución Local
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000


```

## Ejecución con Docker
```bash
docker build -t hc-scan-ocr-service .
docker run -p 8000:8000 hc-scan-ocr-service
```
