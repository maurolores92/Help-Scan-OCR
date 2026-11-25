import re
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

# Configurar sys.path dinámicamente para imports limpios tanto como paquete como script
_cur_dir = Path(__file__).resolve().parent
_app_dir = _cur_dir.parent
_service_root = _app_dir.parent
for _p in (str(_service_root), str(_app_dir), str(_cur_dir)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from app.models.schemas import ExtractionResponse, DocumentArticleItem
    from app.extractors.item_extractor import clean_amount, extract_items_from_text
except ImportError:
    from models.schemas import ExtractionResponse, DocumentArticleItem
    from extractors.item_extractor import clean_amount, extract_items_from_text


SPANISH_MONTHS = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "setiembre": "09", "octubre": "10",
    "noviembre": "11", "diciembre": "12",
}

DOCUMENT_TYPE_RULES = [
    ("nota_credito", re.compile(r"\b(nota\s+de\s+cr[eé]dito|credit\s+note|\bn\.?\s*c\.?\s*[abcme]\b|c[oó]d\.?\s*(?:0?03|0?08|0?13|0?53|203|208|213)\b)", re.IGNORECASE)),
    ("nota_debito", re.compile(r"\b(nota\s+de\s+d[eé]bito|debit\s+note|\bn\.?\s*d\.?\s*[abcme]\b|c[oó]d\.?\s*(?:0?02|0?07|0?12|0?52|202|207|212)\b)", re.IGNORECASE)),
    ("certificado_retencion", re.compile(r"\b(certificado\s+de\s+retenci[oó]n|constancia\s+de\s+retenci[oó]n|agente\s+de\s+retenci[oó]n|sicore|sire\b)", re.IGNORECASE)),
    ("orden_pago", re.compile(r"\b(orden\s+de\s+pago)\b", re.IGNORECASE)),
    ("transferencia_pago", re.compile(r"\b(comprobante\s+de\s+transferencia|transferencia\s+bancaria|id\s*coelsa|comprobante\s+de\s+dep[oó]sito|debin\b)", re.IGNORECASE)),
    ("ticket_fiscal", re.compile(r"\b(tique\s+factura|ticket\s+factura|controlador\s+fiscal|tique\s+consumidor\s+final|c[oó]d\.?\s*(?:0?81|0?82|0?83|111)\b)", re.IGNORECASE)),
    ("factura", re.compile(r"\b(factura|invoice|comprobante\s+electr[oó]nico|cae\b)", re.IGNORECASE)),
    ("presupuesto", re.compile(r"\b(presupuesto|cotizaci[oó]n|quotation)", re.IGNORECASE)),
    ("nota_pedido", re.compile(r"\b(nota\s+de\s+pedido|solicitud\s+de\s+compra)", re.IGNORECASE)),
    ("orden_compra", re.compile(r"\b(orden\s+de\s+compra|purchase\s+order|\bo[\.\s]?c[\.\s]?\b)", re.IGNORECASE)),
    ("remito", re.compile(r"\b(remito|gu[ií]a\s+de\s+despacho|entrega\s+de\s+mercader[ií]a)", re.IGNORECASE)),
    ("recibo", re.compile(r"\b(recibo|comprobante\s+de\s+pago)", re.IGNORECASE)),
    ("orden_servicio", re.compile(r"\b(servicio\s+t[eé]cnico|orden\s+de\s+servicio|parte\s+t[eé]cnico|informe\s+t[eé]cnico)", re.IGNORECASE)),
    ("contrato", re.compile(r"\b(contrato|acuerdo|convenio|cl[aá]usula)", re.IGNORECASE)),
    ("legajo", re.compile(r"\b(legajo|curr[ií]culum|recibo\s+de\s+haberes|alta\s+temprana)", re.IGNORECASE)),
]


def parse_date(text: str) -> Optional[str]:
    if not text:
        return None

    # 1. Textual: "20 de abril de 2022", "15 de junio de 2023"
    textual = re.search(
        r"\b(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+(20\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if textual:
        day = textual.group(1).zfill(2)
        month = SPANISH_MONTHS.get(textual.group(2).lower(), "01")
        year = textual.group(3)
        return f"{year}-{month}-{day}"

    # 2. ISO YYYY-MM-DD
    iso = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])\b", text)
    if iso:
        return iso.group(0)

    # 3. DD/MM/YYYY o DD-MM-YYYY
    latam = re.search(
        r"(?:^|[^\d])(0?[1-9]|[12]\d|3[01])[\/\-](0?[1-9]|1[0-2])[\/\-](20\d{2})\b",
        text,
    )
    if latam:
        day = latam.group(1).zfill(2)
        month = latam.group(2).zfill(2)
        year = latam.group(3)
        return f"{year}-{month}-{day}"

    return None


CLIENT_SECTION_RE = re.compile(
    r"(?:apellido\s+y\s+nombre(?:\s*\/\s*raz[oó]n\s+social)?|se[ñn]or(?:es)?|cliente|destinatario|comprador)\s*[:.]",
    re.IGNORECASE,
)
CORPORATE_NAME_RE = re.compile(
    r"\b(?:S\.?\s*A\.?\s*S?\.?|S\.?\s*R\.?\s*L\.?|S\.?\s*C\.?\s*A\.?|S\.?\s*H\.?|COOPERATIVA|FUNDACI[OÓ]N|ASOCIACI[OÓ]N|HELP\s*COPIES)\b",
    re.IGNORECASE,
)
NON_COMPANY_HEADER_RE = re.compile(
    r"^(?:factura|remito|presupuesto|nota\s+de|recibo|orden\s+de|original|duplicado|triplicado|afip|arca|comprobante|fecha|cuit|punto\s+de\s+venta|ingresos\s+brutos|iva\b)",
    re.IGNORECASE,
)


FISCAL_ISSUER_HINT_RE = re.compile(
    r"\b(?:punto\s+de\s+venta|pto\.?\s*vta|ingresos\s+brutos|inicio\s+de\s+actividades|domicilio\s+comercial|original|duplicado|c\.?a\.?e\.?)\b",
    re.IGNORECASE,
)


def _split_header_and_client(text: str) -> tuple[str, str]:
    match = CLIENT_SECTION_RE.search(text)
    if match:
        header = text[: match.start()].strip()
        client = text[match.start() : match.start() + 450].strip()
        return header, client
    return text[:1200].strip(), ""


def _clean_party_name(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    cleaned = re.split(
        r"\b(?:c\.?u\.?i\.?t\.?|d\.?n\.?i\.?|domicilio|direcci[oó]n|condici[oó]n|iva)\b",
        raw,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    cleaned = re.sub(r"\d{5,}.*$", "", cleaned).strip(" :-–—\t")
    return cleaned if len(cleaned) >= 2 else None


def classify_and_extract_metadata(
    raw_text: str,
    original_file_name: str,
    page_count: int,
    engine: str = "python_pymupdf_native",
) -> ExtractionResponse:
    clean_text = raw_text or ""

    # Clasificación de tipo
    detected_type = "otro"
    name_and_text = f"{original_file_name} {clean_text}"
    for doc_type, pattern in DOCUMENT_TYPE_RULES:
        if pattern.search(name_and_text):
            detected_type = doc_type
            break

    # Fechas
    document_date = parse_date(clean_text)

    # Vencimiento
    due_date = None
    vto_match = re.search(
        r"(?:vencimiento|vto\.?|validez(?:\s+de\s+la\s+propuesta)?|hasta)[:\s]*([^\n\r]{4,40})",
        clean_text,
        re.IGNORECASE,
    )
    if vto_match:
        due_date = parse_date(vto_match.group(1))

    # Número de comprobante / documento
    doc_num_match = (
        re.search(r"(?:Nro\.?|N[úu]mero|N°|Punto\s+de\s+Venta\s+Comp\.)[:\s]*([0-9]{4,5}-[0-9]{6,8})", clean_text, re.IGNORECASE)
        or re.search(r"\b([0-9]{4,5}-[0-9]{6,8})\b", clean_text)
        or re.search(r"(?:Nro\.?|N[úu]mero|N°)[:\s]*([0-9]{1,12})\b", clean_text, re.IGNORECASE)
    )
    document_number = doc_num_match.group(1).replace(" ", "") if doc_num_match else None

    # CUIT
    tax_id_matches = re.findall(r"\b\d{2}-\d{8}-\d\b", clean_text)
    primary_tax_id = tax_id_matches[0] if tax_id_matches else None
    secondary_tax_id = tax_id_matches[1] if len(tax_id_matches) > 1 else None

    header_block, client_block_raw = _split_header_and_client(clean_text)
    has_explicit_client_block = bool(client_block_raw)
    has_fiscal_issuer_header = bool(FISCAL_ISSUER_HINT_RE.search(header_block))

    # Emisor (siempre en cabecera superior, o explícito con Proveedor/Emisor/Empresa).
    # En presupuestos/notas sin bloque cliente ni cabecera fiscal AFIP, "Razón social:" pertenece al destinatario.
    issuer_match = re.search(r"(?:proveedor|emisor|empresa)\s*:\s*([^\n]{3,90})", clean_text, re.IGNORECASE)
    if not issuer_match and (has_explicit_client_block or has_fiscal_issuer_header):
        issuer_match = re.search(
            r"(?:raz[oó]n\s+social|denominaci[oó]n)\s*:\s*([^\n]{3,90})",
            header_block,
            re.IGNORECASE,
        )
    issuer_name = _clean_party_name(issuer_match.group(1)) if issuer_match else None
    if not issuer_name and re.search(r"HELP\s*COPIES", header_block or clean_text, re.IGNORECASE):
        issuer_name = "HELP COPIES S.R.L."
    if not issuer_name and header_block:
        for h_line in [l.strip() for l in header_block.split("\n") if l.strip()][:12]:
            if NON_COMPANY_HEADER_RE.match(h_line):
                continue
            if re.match(r"^(?:raz[oó]n\s+social|cliente|se[ñn]or(?:es)?)\s*:", h_line, re.IGNORECASE):
                continue
            if CORPORATE_NAME_RE.search(h_line):
                candidate_issuer = _clean_party_name(h_line)
                if candidate_issuer:
                    issuer_name = candidate_issuer
                    break

    # Cliente / Receptor (nunca capturar la Razón Social del encabezado emisor)
    recipient_match = re.search(
        r"(?:apellido\s+y\s+nombre(?:\s*\/\s*raz[oó]n\s+social)?|se[ñn]or(?:es)?|cliente|destinatario|comprador)[:\s]*([^\n\r]{3,90})",
        clean_text,
        re.IGNORECASE,
    )
    if not recipient_match:
        if client_block_raw:
            recipient_match = re.search(r"raz[oó]n\s+social[:\s]*([^\n\r]{3,90})", client_block_raw, re.IGNORECASE)
        elif not has_fiscal_issuer_header:
            recipient_match = re.search(r"raz[oó]n\s+social[:\s]*([^\n\r]{3,90})", clean_text, re.IGNORECASE)

    recipient_name = _clean_party_name(recipient_match.group(1)) if recipient_match else None
    if recipient_name and issuer_name and recipient_name.lower() == issuer_name.lower():
        recipient_name = None

    # Detectar si hay un CUIT ubicado dentro del bloque de cliente / señores
    client_cuit = None
    client_block = re.search(
        r"(?:apellido\s+y\s+nombre(?:\s*\/\s*raz[oó]n\s+social)?|se[ñn]or(?:es)?|cliente|destinatario|comprador)[:\s]*([\s\S]{1,280}?)(?:\b(?:transferencia|c\.?a\.?e\.?|precio|total|subtotal|act:)\b|$)",
        clean_text,
        re.IGNORECASE,
    )
    if client_block:
        c_found = re.findall(r"\b\d{2}-\d{8}-\d\b", client_block.group(0))
        if c_found:
            client_cuit = c_found[0]

    header_cuits = re.findall(r"\b\d{2}-\d{8}-\d\b", header_block)
    if client_cuit:
        recipient_tax_id = client_cuit
        issuer_tax_id = next((c for c in header_cuits if c != client_cuit), None) or next(
            (c for c in tax_id_matches if c != client_cuit), None
        )
        if not issuer_tax_id and issuer_name and "HELP" in issuer_name.upper():
            issuer_tax_id = ""
    else:
        if issuer_name and "HELP" in issuer_name.upper():
            issuer_tax_id = ""
            recipient_tax_id = primary_tax_id
        else:
            issuer_tax_id = header_cuits[0] if header_cuits else primary_tax_id
            recipient_tax_id = secondary_tax_id if issuer_tax_id == primary_tax_id else primary_tax_id

    # CAE de AFIP (14 dígitos)
    cae_match = re.search(r"C\.?A\.?E\.?[:\s]*(\d{14})", clean_text, re.IGNORECASE)
    cae = cae_match.group(1) if cae_match else None

    # Condición fiscal
    tax_cond_match = re.search(
        r"\b(responsable\s*inscripto|monotributo|exento|consumidor\s*final)\b",
        clean_text,
        re.IGNORECASE,
    )
    tax_condition = tax_cond_match.group(1) if tax_cond_match else None

    # ID y Modelo de equipo
    equip_id_match = re.search(r"\bID[:\s]*(\d{2,10})\b", clean_text, re.IGNORECASE)
    equipment_id = equip_id_match.group(1) if equip_id_match else None

    equip_model_match = (
        re.search(r"Equipo[:\s]*([^,\n\r\t]+?)(?:\s+ID[:\s]|\n|$)", clean_text, re.IGNORECASE)
        or re.search(r"\b(MP\s*\d+\s*[A-Z]*|M320F|E52645|LaserJet[A-Za-z0-9\s-]+)\b", clean_text, re.IGNORECASE)
    )
    equipment_model = equip_model_match.group(1).strip() if equip_model_match else None

    # Contador
    meter_match = re.search(r"ACT[:\s]*(\d+)\s*-\s*ANT[:\s]*(\d+)", clean_text, re.IGNORECASE)
    meter_count = f"ACT:{meter_match.group(1)} - ANT:{meter_match.group(2)}" if meter_match else None

    # Moneda
    currency = "USD" if ("USD" in clean_text or "U$S" in clean_text or "dolares" in clean_text.lower()) else "ARS"

    # Importes
    total_amount = None
    tot_match = re.search(r"(?:total|importe\s+total|total\s+hc)\s*[:\-\s$]{1,6}([\d.,]{2,18})", clean_text, re.IGNORECASE)
    if tot_match:
        total_amount = clean_amount(tot_match.group(1))

    # Si no hubo match explícito de total, buscar último importe significativo
    if total_amount is None:
        last_amounts = re.findall(r"\$?\s*([0-9]{1,3}(?:\.[0-9]{3})*,[0-9]{2}|[0-9]{1,7}\.[0-9]{2})\b", clean_text)
        if last_amounts:
            total_amount = clean_amount(last_amounts[-1])

    tax_amount = None
    iva_match = re.search(r"(?:iva|21%|10\.5%)\s*[:$]?\s*([\d.,]{2,18})", clean_text, re.IGNORECASE)
    if iva_match:
        tax_amount = clean_amount(iva_match.group(1))

    net_amount = None
    subtotal_match = re.search(r"(?:subtotal|neto|sub-total)\s*[:$]?\s*([\d.,]{2,18})", clean_text, re.IGNORECASE)
    if subtotal_match:
        net_amount = clean_amount(subtotal_match.group(1))
    elif total_amount is not None and tax_amount is not None and total_amount >= tax_amount:
        net_amount = round(total_amount - tax_amount, 2)
    else:
        sub_m = re.search(r"([\d.,]+)\s+(?:0\.00\s+)?(?:21%|10\.5%)", clean_text)
        if sub_m:
            net_amount = clean_amount(sub_m.group(1))

    # Teléfono
    phone_match = re.search(r"(?:tel[eé]fono|celular|tel|cel)[:\s]*([0-9\s\(\)\-\+]{6,25})", clean_text, re.IGNORECASE)
    recipient_phone = phone_match.group(1).strip() if phone_match else None

    # Email
    email_match = re.search(r"(?:e-?mail|correo)[:\s]*([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", clean_text, re.IGNORECASE)
    recipient_email = email_match.group(1).strip() if email_match else None

    # Domicilio
    addr_match = re.search(r"(?:domicilio|direcci[oó]n|entrega\s+en)[:\s]*([^\n\r]{4,100})", clean_text, re.IGNORECASE)
    loc_match = re.search(r"Localidad[:\s]*([^\n\r]{3,60})", clean_text, re.IGNORECASE)
    delivery_address = None
    if addr_match and loc_match:
        delivery_address = f"{addr_match.group(1).strip()}, {loc_match.group(1).strip()}"
    elif addr_match:
        delivery_address = addr_match.group(1).strip()
    elif loc_match:
        delivery_address = loc_match.group(1).strip()

    # Responsable / Contacto / Firma
    resp_match = (
        re.search(r"(?:saluda\s*(?:a\s*usted\s*)?atte:?)\s*([A-Za-zÁÉÍÓÚáéíóúÑñ\s]{3,50})", clean_text, re.IGNORECASE)
        or re.search(r"(?:contacto|vendedor|responsable|solicitante|autorizado\s+por|firmante)\s*:\s*([^\n\r]{3,60})", clean_text, re.IGNORECASE)
        or re.search(r"(?<!servicio\s)(?<!soporte\s)\bt[eé]cnico\s*:\s*([^\n\r]{3,60})", clean_text, re.IGNORECASE)
    )
    responsible_person = resp_match.group(1).strip() if resp_match else None

    # Forma de pago
    pay_terms_match = re.search(
        r"(?:forma\s+de\s+pago|condici[oó]n\s+de\s+venta|cta\.?\s*cte\.?|validez(?:\s+de\s+la\s+propuesta)?)[:\s]*([^\n\r]{3,100})",
        clean_text,
        re.IGNORECASE,
    )
    payment_terms = pay_terms_match.group(1).strip() if pay_terms_match else None

    payment_method = None
    if re.search(r"transferencia", clean_text, re.IGNORECASE):
        payment_method = "Transferencia Bancaria"
    elif re.search(r"cheque", clean_text, re.IGNORECASE):
        payment_method = "Cheque"
    elif re.search(r"efectivo", clean_text, re.IGNORECASE):
        payment_method = "Efectivo"

    # Atributos dinámicos
    attributes: Dict[str, Any] = {}
    lines = [l.strip() for l in clean_text.split("\n") if l.strip()]
    for line in lines[:60]:
        kv = re.match(r"^([A-Za-zÁÉÍÓÚáéíóúÑñ0-9\s./()-]{2,35}):\s*(.{1,100})$", line)
        if kv:
            key = kv.group(1).strip().lower().replace(" ", "_")
            if key not in attributes and len(attributes) < 20:
                attributes[key] = kv.group(2).strip()

    if equipment_id:
        attributes["equipo_id"] = equipment_id
    if meter_count:
        attributes["contador"] = meter_count
    if cae:
        attributes["cae"] = cae

    # Tags
    tags: List[str] = [detected_type]
    if equipment_id:
        tags.append(f"id_{equipment_id}")
    if detected_type == "factura":
        tags.append("afip")
    if engine == "python_tesseract_ocr":
        tags.append("escaneo_ocr")

    # Extraer ítems
    extracted_items = extract_items_from_text(clean_text)

    # Resumen
    first_lines = " · ".join(lines[:3])[:220]
    summary = (
        f"Documento clasificado como {detected_type.replace('_', ' ')}. {first_lines}"
        if len(clean_text) > 20
        else f"Archivo PDF registrado ({original_file_name}). Procesado con motor {engine}."
    )

    return ExtractionResponse(
        document_type=detected_type,
        summary=summary,
        document_number=document_number,
        document_date=document_date,
        due_date=due_date,
        issuer_name=issuer_name,
        issuer_tax_id=issuer_tax_id,
        recipient_name=recipient_name,
        recipient_tax_id=recipient_tax_id,
        recipient_phone=recipient_phone,
        recipient_email=recipient_email,
        delivery_address=delivery_address,
        responsible_person=responsible_person,
        currency=currency if total_amount is not None else None,
        net_amount=net_amount,
        tax_amount=tax_amount,
        total_amount=total_amount,
        payment_terms=payment_terms,
        payment_method=payment_method,
        reference_number=None,
        cae=cae,
        tax_condition=tax_condition,
        equipment_id=equipment_id,
        equipment_model=equipment_model,
        meter_count=meter_count,
        tags=tags,
        items=extracted_items,
        extracted_data={
            "attributes": attributes,
            "items": [it.model_dump(by_alias=False) for it in extracted_items],
            "involvedParties": [
                {"name": issuer_name or "Desconocido", "role": "emisor", "identifier": issuer_tax_id},
                {"name": recipient_name or "Desconocido", "role": "receptor", "identifier": recipient_tax_id},
            ],
            "dates": {"vencimiento": due_date} if due_date else {},
            "amounts": {"subtotal": net_amount or 0, "impuestos": tax_amount or 0},
        },
        raw_text=clean_text,
        page_count=page_count,
        ai_confidence=0.95,
        extraction_engine=engine,
        tokens_used=0,
    )
