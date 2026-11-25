import re
import sys
from pathlib import Path
from typing import List, Optional

# Configurar sys.path dinámicamente para imports limpios tanto como paquete como script
_cur_dir = Path(__file__).resolve().parent
_app_dir = _cur_dir.parent
_service_root = _app_dir.parent
for _p in (str(_service_root), str(_app_dir), str(_cur_dir)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from app.models.schemas import DocumentArticleItem
except ImportError:
    from models.schemas import DocumentArticleItem


IGNORED_ITEM_PATTERNS = [
    re.compile(r"\b3\d-\d{8}-\d\b"),                          # CUIT
    re.compile(r"transferencia\s+bancaria|cbu\s*\d|alias\s*:", re.IGNORECASE),
    re.compile(r"c\.?a\.?e\.?|vto\.|original|duplicado", re.IGNORECASE),
    re.compile(r"\b\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\s+de\s+20\d{2}\b", re.IGNORECASE),
    re.compile(r"@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", re.IGNORECASE),
    re.compile(r"celular|tel[eé]fono|domicilio|localidad|direcci[oó]n", re.IGNORECASE),
    re.compile(r"^(?:total|subtotal|iva|neto|importe)\b", re.IGNORECASE),
]


def clean_amount(val_str: Optional[str]) -> Optional[float]:
    if not val_str:
        return None
    cleaned = str(val_str).replace("$", "").replace(" ", "").strip()
    if not cleaned:
        return None

    # Si contiene punto y coma (ej. 39.520,00)
    if "." in cleaned and "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        # En formatos es-AR/LATAM, grupos exactos de miles sin coma decimal (ej: 154.200, 36.500, 1.250.000)
        if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", cleaned):
            cleaned = cleaned.replace(".", "")
        else:
            parts = cleaned.split(".")
            if len(parts) > 2:
                cleaned = "".join(parts[:-1]) + "." + parts[-1]

    try:
        val = float(cleaned)
        return val if val >= 0 else None
    except ValueError:
        return None


def extract_items_from_text(text: str) -> List[DocumentArticleItem]:
    items: List[DocumentArticleItem] = []
    if not text:
        return items

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Patrón 1: ERP compacto AFIP (ej: 800000001ALQUILEREQUIPO1.0039520.00039520.00)
    erp_compact_regex = re.compile(
        r"^(\d{6,14})([A-Za-zÁÉÍÓÚáéíóúÑñ\s\-\.]{3,40}?)(\d+(?:\.\d{1,2})?)(\d+(?:\.\d{2})?)(\d+(?:\.\d{2})?)$"
    )

    # Patrón 2: Con prefijo de código (ej: HC 1 - M320F $ 235000 21 % $ 49350 $ 284350)
    prefixed_regex = re.compile(
        r"^([A-Z]{1,4}\s*\d+)\s*-\s*([A-Za-z0-9\s\-\.\/]+?)\s+\$?\s*([\d\.,]+)(?:\s+(\d+)\s*%)?(?:\s+\$?\s*([\d\.,]+))?(?:\s+\$?\s*([\d\.,]+))?$",
        re.IGNORECASE,
    )

    # Patrón 3: Con viñeta (opcional) y cantidad entre paréntesis (ej: UNI FOTOCONDUCTORA MP 201-1515 (1))
    parenthesis_regex = re.compile(
        r"^(?:[•·\-\*]\s*)?([A-Za-z0-9ÁÉÍÓÚáéíóúÑñ\s\-\.\/]+?)\s*\((\d+)\)$"
    )

    # Patrón 4: Tabular con columnas en la misma línea (ej: ART-001  Toner Ricoh Black  2  15000.00  30000.00)
    tabular_regex = re.compile(
        r"^([A-Z0-9\-_]{2,12})\s+([A-Za-z0-9ÁÉÍÓÚáéíóúÑñ\s\-\.]{3,45})\s+(\d+(?:[\.,]\d{1,2})?)\s+\$?\s*([\d\.,]{3,12})\s+\$?\s*([\d\.,]{3,12})$"
    )

    # Procesar líneas
    i = 0
    while i < len(lines):
        line = lines[i]

        if any(pat.search(line) for pat in IGNORED_ITEM_PATTERNS):
            i += 1
            continue

        # A) Bloque multilínea ERP / AFIP (Código numérico en línea propia seguido de descripción y montos)
        # Ejemplo:
        # 800000001
        # ALQUILER EQUIPO
        # 1.00
        # 39520.000
        # 39520.00
        if re.match(r"^\d{6,14}$", line):
            code = line
            if (
                i + 1 < len(lines)
                and re.match(r"^[A-Za-zÁÉÍÓÚáéíóúÑñ0-9\s\-\.\/]{3,60}$", lines[i + 1])
                and not any(p.search(lines[i + 1]) for p in IGNORED_ITEM_PATTERNS)
            ):
                desc = lines[i + 1]
                qty = 1.0
                unit_p = None
                tot_p = None
                consumed = 2

                if i + 2 < len(lines) and re.match(r"^\d+(?:\.\d+)?$", lines[i + 2]):
                    qty = clean_amount(lines[i + 2]) or 1.0
                    consumed = 3
                if i + 3 < len(lines) and re.match(r"^\d+(?:\.\d+)?$", lines[i + 3]):
                    unit_p = clean_amount(lines[i + 3])
                    consumed = 4
                if i + 4 < len(lines) and re.match(r"^\d+(?:\.\d+)?$", lines[i + 4]):
                    tot_p = clean_amount(lines[i + 4])
                    consumed = 5

                items.append(
                    DocumentArticleItem(
                        codigo=code,
                        nombre=desc,
                        cantidad=qty,
                        precio_sin_iva=unit_p,
                        precio_final=tot_p or unit_p,
                        iva_porcentaje=None,
                    )
                )
                i += consumed
                continue

        # B) Patrón con cantidad en paréntesis (ej: UNI FOTOCONDUCTORA MP 201-1515 (1))
        paren_match = parenthesis_regex.match(line)
        if paren_match:
            desc = paren_match.group(1).strip()
            qty = float(paren_match.group(2))
            if len(desc) >= 3 and not any(p.search(desc) for p in IGNORED_ITEM_PATTERNS):
                items.append(
                    DocumentArticleItem(
                        codigo=None,
                        nombre=desc,
                        cantidad=qty,
                        precio_sin_iva=None,
                        precio_final=None,
                        iva_porcentaje=None,
                    )
                )
                i += 1
                continue

        # C) ERP compacto en una sola línea (ej: 800000001ALQUILEREQUIPO1.0039520.00039520.00)
        erp_match = erp_compact_regex.match(line)
        if erp_match:
            code = erp_match.group(1)
            desc = erp_match.group(2).strip()
            qty = clean_amount(erp_match.group(3)) or 1.0
            unit_p = clean_amount(erp_match.group(4))
            tot_p = clean_amount(erp_match.group(5)) or unit_p

            if len(desc) >= 3 and not any(p.search(desc) for p in IGNORED_ITEM_PATTERNS):
                items.append(
                    DocumentArticleItem(
                        codigo=code,
                        nombre=desc,
                        cantidad=qty,
                        precio_sin_iva=unit_p,
                        precio_final=tot_p,
                        iva_porcentaje=None,
                    )
                )
                i += 1
                continue

        # D) Prefijo de código (HC 1 - M320F)
        pref_match = prefixed_regex.match(line)
        if pref_match:
            code = pref_match.group(1).replace(" ", "")
            desc = pref_match.group(2).strip()
            val1 = clean_amount(pref_match.group(3))
            iva_pct = float(pref_match.group(4)) if pref_match.group(4) else None
            val_iva = clean_amount(pref_match.group(5))
            val_total = clean_amount(pref_match.group(6))

            unit_p = val1
            tot_p = val_total or (unit_p + val_iva if val_iva and unit_p else unit_p)

            items.append(
                DocumentArticleItem(
                    codigo=code,
                    nombre=desc,
                    cantidad=1.0,
                    precio_sin_iva=unit_p,
                    precio_final=tot_p,
                    iva_porcentaje=iva_pct,
                )
            )
            i += 1
            continue

        # E) Tabular multi-industria en una sola línea
        tab_match = tabular_regex.match(line)
        if tab_match:
            code = tab_match.group(1).strip()
            desc = tab_match.group(2).strip()
            qty = clean_amount(tab_match.group(3)) or 1.0
            unit_p = clean_amount(tab_match.group(4))
            tot_p = clean_amount(tab_match.group(5))

            if len(desc) >= 3 and not any(p.search(desc) for p in IGNORED_ITEM_PATTERNS):
                items.append(
                    DocumentArticleItem(
                        codigo=code,
                        nombre=desc,
                        cantidad=qty,
                        precio_sin_iva=unit_p,
                        precio_final=tot_p,
                        iva_porcentaje=None,
                    )
                )
                i += 1
                continue

        i += 1

    return items
