"""
Módulo de parseo de cronogramas y designaciones de partidos en formato PDF.
Extrae partidos de las secciones MENORES, MAYORES, MAXI 30 y REPROGRAMADOS de la Federación de Cestoball de Capital Federal.
Soporta PDFs con capas de texto estándar y PDFs con fuentes vectoriales/incrustadas vía OCR automático.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Union

import pymupdf
import pypdf

try:
    from rapidocr_onnxruntime import RapidOCR
    _ocr_engine = RapidOCR()
except Exception:
    _ocr_engine = None

KNOWN_CATEGORIES = [
    "SUB10", "SUB 10", "SUB12", "SUB 12", "SUB14 FLEX", "SUB 14 FLEX", "SUB14", "SUB 14",
    "SUB17 FLEX", "SUB 17 FLEX", "SUB17", "SUB 17", "SUB20", "SUB 20",
    "PRIMERA A", "PRIMERA B", "PRIMERA MASCULINO", "MASCULINO",
    "MAXI 30", "MAXI30", "MAXI 35", "MAXI35", "MAXI 40", "MAXI40"
]


def normalize_category(cat: str) -> str:
    cat = cat.upper().strip()
    cat = re.sub(r"\bSUB(\d+)", r"SUB \1", cat)
    cat = re.sub(r"\bMAXI(\d+)", r"MAXI \1", cat)
    if cat == "MASCULINO":
        cat = "PRIMERA MASCULINO"
    return re.sub(r"\s+", " ", cat)


def parse_schedule_line(line: str, current_division: str) -> Dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None

    # Check date pattern: e.g. "   7   26/09/2026   ..."
    m = re.match(r"^(\d+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(.+)$", line)
    if not m:
        return None

    round_num = int(m.group(1))
    match_date = m.group(2)
    rest = m.group(3).strip()

    # Find time: e.g. 9:00, 19:30, 20:45
    time_match = re.search(r"(\b\d{1,2}:\d{2}\b)", rest)
    if not time_match:
        return None

    time_str = time_match.group(1)
    time_pos = time_match.start()
    time_end = time_match.end()

    before_time = rest[:time_pos].strip()
    after_time = rest[time_end:].strip()

    # Find category in before_time
    cat_found = None
    cat_pos = -1
    for cat in sorted(KNOWN_CATEGORIES, key=len, reverse=True):
        idx = before_time.upper().rfind(cat.upper())
        if idx != -1:
            cat_found = cat
            cat_pos = idx
            break

    if not cat_found:
        return None

    teams_and_venue = before_time[:cat_pos].strip()
    category_str = before_time[cat_pos:].strip()
    norm_cat = normalize_category(category_str)

    # In layout extraction, multiple spaces or tabs separate columns: Local, Visitante, Sede
    col_parts = [p.strip() for p in re.split(r"\s{2,}|\t", teams_and_venue) if p.strip()]
    
    home_team = ""
    away_team = ""
    venue = ""

    if len(col_parts) >= 3:
        home_team = col_parts[0]
        away_team = col_parts[1]
        venue = col_parts[2]
    elif len(col_parts) == 2:
        home_team = col_parts[0]
        away_team = col_parts[1]
        venue = home_team
    elif len(col_parts) == 1:
        tokens = col_parts[0].split()
        if len(tokens) >= 2:
            home_team = tokens[0]
            away_team = " ".join(tokens[1:])
        else:
            home_team = col_parts[0]
            away_team = ""
        venue = ""

    # Parse referees and observations from after_time
    # Handle glued parenthesis e.g. "Sergio Sourigues (A)Reprogramado..."
    after_time_clean = re.sub(r"(\([A-Za-z0-9]\))([A-Za-z])", r"\1   \2", after_time)
    after_parts = [p.strip() for p in re.split(r"\s{2,}|\t", after_time_clean) if p.strip()]
    ref1 = ""
    ref2 = ""
    obs = ""

    if len(after_parts) == 1:
        if any(w in after_parts[0].lower() for w in ["local", "sede", "reprogramado", "cede", "cancha", "vs", "postergado", "yom", "dia del perdon"]):
            obs = after_parts[0]
        else:
            ref1 = after_parts[0]
    elif len(after_parts) == 2:
        ref1 = after_parts[0]
        if any(w in after_parts[1].lower() for w in ["local", "sede", "reprogramado", "cede", "cancha", "yom", "dia del perdon"]):
            obs = after_parts[1]
        else:
            ref2 = after_parts[1]
    elif len(after_parts) >= 3:
        ref1 = after_parts[0]
        ref2 = after_parts[1]
        obs = " ".join(after_parts[2:])

    is_sitas = ("SITAS" in home_team.upper()) or ("SITAS" in away_team.upper())

    return {
        "division": current_division,
        "round_num": round_num,
        "match_date": match_date,
        "time": time_str,
        "category": norm_cat,
        "home_team": home_team,
        "away_team": away_team,
        "venue": venue,
        "ref1": ref1,
        "ref2": ref2,
        "observations": obs,
        "is_sitas": is_sitas
    }


def parse_schedule_with_ocr(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parsea partidos rasterizando las páginas y utilizando OCR para PDFs sin tabla ToUnicode estándar.
    """
    if not _ocr_engine:
        return []

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    matches: List[Dict[str, Any]] = []
    current_division = "MENORES"

    for page in doc:
        pix = page.get_pixmap(dpi=200)
        res, _ = _ocr_engine(pix.tobytes("png"))
        if not res:
            continue

        items = []
        for box, text, _score in res:
            y_center = (box[0][1] + box[2][1]) / 2
            x_left = box[0][0]
            items.append((y_center, x_left, text.strip()))
        items.sort(key=lambda item: item[0])

        lines = []
        curr_line = []
        curr_y = None
        for y, x, text in items:
            if curr_y is None or abs(y - curr_y) < 14:
                curr_line.append((x, text))
                curr_y = y if curr_y is None else (curr_y + y) / 2
            else:
                curr_line.sort(key=lambda it: it[0])
                lines.append("   ".join([t for _, t in curr_line]))
                curr_line = [(x, text)]
                curr_y = y
        if curr_line:
            curr_line.sort(key=lambda it: it[0])
            lines.append("   ".join([t for _, t in curr_line]))

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            u = line_str.upper()
            if "MAXI" in u and len(line_str) < 25:
                current_division = "MAXI 30"
                continue
            elif "MENORES" in u and "MAYORES" in u and len(line_str) < 35:
                current_division = "MENORES Y MAYORES"
                continue
            elif "MAYORES" in u and len(line_str) < 25:
                current_division = "MAYORES"
                continue
            elif "MENORES" in u and len(line_str) < 25:
                current_division = "MENORES"
                continue

            match_data = parse_schedule_line(line_str, current_division)
            if match_data:
                matches.append(match_data)

    return matches


def parse_schedule_pdf(pdf_source: Union[str, Path, BinaryIO, bytes]) -> List[Dict[str, Any]]:
    """
    Lee un archivo PDF (ruta, stream de bytes o buffer) y devuelve la lista de partidos estructurados.
    Primero intenta la extracción de texto nativa directa; si el archivo carece de fuentes
    estándar o no encuentra partidos, conmuta automáticamente a extracción con OCR.
    """
    raw_bytes: bytes
    if isinstance(pdf_source, (str, Path)):
        raw_bytes = Path(pdf_source).read_bytes()
    elif isinstance(pdf_source, bytes):
        raw_bytes = pdf_source
    else:
        raw_bytes = pdf_source.read()

    # 1. Intentar extracción de texto estándar con pypdf
    matches: List[Dict[str, Any]] = []
    try:
        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        current_division = "MENORES"

        for page in reader.pages:
            try:
                text = page.extract_text(extraction_mode="layout")
            except Exception:
                text = page.extract_text()

            if not text:
                continue

            lines = text.splitlines()
            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue

                u = line_str.upper()
                if "MAXI" in u and len(line_str) < 25:
                    current_division = "MAXI 30"
                    continue
                elif "MENORES" in u and "MAYORES" in u and len(line_str) < 35:
                    current_division = "MENORES Y MAYORES"
                    continue
                elif "MAYORES" in u and len(line_str) < 25:
                    current_division = "MAYORES"
                    continue
                elif "MENORES" in u and len(line_str) < 25:
                    current_division = "MENORES"
                    continue

                if "FECHA #" in line_str or "ARBITRO" in line_str:
                    continue

                match_data = parse_schedule_line(line_str, current_division)
                if match_data:
                    matches.append(match_data)
    except Exception:
        matches = []

    # 2. Si no se encontraron partidos con el texto nativo (por fuentes Type3 / imágenes), recurrir al OCR
    if not matches:
        matches = parse_schedule_with_ocr(raw_bytes)

    return matches
