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
    "PRIMERA A", "PRIMERA B", "PRIMERAA", "PRIMERAB", "PRIMERA MASCULINO", "MASCULINO", "MASCUUNO",
    "MAXI 30", "MAXI30", "MAXI 35", "MAXI35", "MAXI 40", "MAXI40"
]

OBSERVATION_KEYWORDS = [
    "por", "si gana", "gana", "bonaerenses", "reprogramado", "postergado", "cede",
    "cancha", "local", "sede", "presenta", "no se presenta", "jugadoras", "judío",
    "judio", "dia", "perdon", "torneo", "partido", "semana", "tienen que", "aviso", "susp"
]


def normalize_category(cat: str) -> str:
    cat = cat.upper().strip()
    cat = re.sub(r"\bSUB(\d+)", r"SUB \1", cat)
    cat = re.sub(r"\bMAXI(\d+)", r"MAXI \1", cat)
    if "MASCUUNO" in cat or cat == "MASCULINO":
        cat = "PRIMERA MASCULINO"
    elif cat == "PRIMERAA":
        cat = "PRIMERA A"
    elif cat == "PRIMERAB":
        cat = "PRIMERA B"
    cat = re.sub(r"\bSUB\s+(\d+)\s*FLEX\b", r"SUB \1 FLEX", cat)
    return re.sub(r"\s+", " ", cat)


def normalize_team_name(name: str) -> str:
    name = name.strip()
    # Corrección de errores OCR típicos
    name = re.sub(r"\bSITA5\b", "SITAS", name, flags=re.IGNORECASE)
    name = re.sub(r"\bSITAS\s+8\b", "SITAS B", name, flags=re.IGNORECASE)
    name = re.sub(r"3[\*\"#']\s*vs\s*6[\*\"#']", "3° vs 6°", name, flags=re.IGNORECASE)
    name = re.sub(r"3[\*\"#']\s*al\s*6[\*\"#']", "3° al 6°", name, flags=re.IGNORECASE)

    # Estandarización de mayúsculas para equipos SITAS
    if re.search(r"^sitas$", name, flags=re.IGNORECASE):
        return "SITAS"
    if re.search(r"^sitas\s+b$", name, flags=re.IGNORECASE):
        return "SITAS B"
    if re.search(r"^sitas\s+flex$", name, flags=re.IGNORECASE):
        return "SITAS FLEX"
    return name


def normalize_venue_name(name: str) -> str:
    name = name.strip()
    if re.search(r"^(SITAS|SITA5|Sitas|sitas)$", name, flags=re.IGNORECASE):
        return "SITAS"
    return name


def is_sitas_team(team_name: str) -> bool:
    """Verifica si el nombre del equipo corresponde a SITAS en cualquiera de sus variantes."""
    if not team_name:
        return False
    # Detecta SITAS, Sitas, sitas, SITAS B, SITAS FLEX, SITA5 (OCR typo), S.I.T.A.S.
    return bool(re.search(r"\b(S\.?I\.?T\.?A\.?S\.?|SITA5)\b", team_name, re.IGNORECASE))


def parse_schedule_line(line: str, current_division: str) -> Dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None

    u = line.upper()
    if any(h in u for h in ["FEDERACION", "FEDERACIÓN", "TORNEO APERTURA", "TORNEO CLAUSURA"]) and len(line) < 60:
        return None
    if ("FECHA#" in u or "FECHA #" in u) and ("LOCAL" in u or "VISITANTE" in u):
        return None
    if u in ("MENORES", "MAYORES", "MAXI 30", "MAXI30", "REPROGRAMADOS"):
        return None

    # Detectar fecha (dd/mm/yyyy o dd/mm/yy o dd-mm-yyyy)
    # Toleramos que OCR haya pegado una palabra antes de la fecha (ej. "Vuelta29/10/2026")
    date_match = re.search(r"((?<!\d)\d{1,2}[/-]\d{1,2}[/-]\d{2,4}(?!\d))", line)
    if not date_match:
        return None

    round_raw = line[:date_match.start()].strip()
    round_clean = re.sub(r"^FECHA\s*#?\s*", "", round_raw, flags=re.IGNORECASE).strip()
    round_clean = re.sub(r"3[9#]\s*Partido", "3° Partido", round_clean, flags=re.IGNORECASE)
    round_val: Union[int, str] = round_clean
    if round_clean.isdigit():
        round_val = int(round_clean)

    match_date = date_match.group(1).replace("-", "/")
    d_parts = match_date.split("/")
    if len(d_parts) == 3:
        day = d_parts[0].zfill(2)
        month = d_parts[1].zfill(2)
        year = d_parts[2]
        if len(year) == 2:
            year = "20" + year
        match_date = f"{day}/{month}/{year}"
    rest = line[date_match.end():].strip()

    # Buscar horario: ej. 9:00, 19:30, 20:45
    time_match = re.search(r"((?<!\d)\d{1,2}:\d{2}(?!\d))", rest)
    if time_match:
        time_str = time_match.group(1)
        time_pos = time_match.start()
        time_end = time_match.end()
        before_time = rest[:time_pos].strip()
        after_time = rest[time_end:].strip()
    else:
        time_str = "-"
        before_time = rest
        after_time = ""

    # Buscar categoría en before_time (o en rest)
    cat_found = None
    cat_pos = -1
    for cat in sorted(KNOWN_CATEGORIES, key=len, reverse=True):
        idx = before_time.upper().rfind(cat.upper())
        if idx != -1:
            cat_found = cat
            cat_pos = idx
            break

    # Fallback si categoría quedó después de horario
    if not cat_found and after_time:
        for cat in sorted(KNOWN_CATEGORIES, key=len, reverse=True):
            idx = after_time.upper().find(cat.upper())
            if idx != -1:
                cat_found = cat
                cat_pos = len(before_time)
                after_time = (after_time[:idx] + " " + after_time[idx + len(cat):]).strip()
                break

    if not cat_found:
        return None

    teams_and_venue = before_time[:cat_pos].strip()
    norm_cat = normalize_category(cat_found)
    extra_after_cat = before_time[cat_pos + len(cat_found):].strip()

    if extra_after_cat:
        after_time = f"{extra_after_cat} {after_time}".strip() if after_time else extra_after_cat

    # Separar equipos y sede por 2 o más espacios o tabulaciones
    col_parts = [p.strip() for p in re.split(r"\s{2,}|\t", teams_and_venue) if p.strip()]

    # Reagrupar sufijos de equipos (A, B, C, FLEX, PROMO, etc.) que hayan quedado separados en una columna
    team_suffixes = {"A", "B", "C", "D", "FLEX", "PROMO"}
    if len(col_parts) >= 4 and col_parts[1].upper() in team_suffixes:
        col_parts[0] = f"{col_parts[0]} {col_parts[1]}"
        col_parts.pop(1)
    if len(col_parts) >= 4 and col_parts[2].upper() in team_suffixes:
        col_parts[1] = f"{col_parts[1]} {col_parts[2]}"
        col_parts.pop(2)

    home_team = ""
    away_team = ""
    venue = ""

    if len(col_parts) >= 3:
        home_team = col_parts[0]
        away_team = col_parts[1]
        venue = " ".join(col_parts[2:])
    elif len(col_parts) == 2:
        home_team = col_parts[0]
        away_team = col_parts[1]
        venue = home_team
    elif len(col_parts) == 1:
        tokens = col_parts[0].split()
        if len(tokens) >= 3 and tokens[0].upper() == tokens[-1].upper():
            home_team = tokens[0]
            away_team = " ".join(tokens[1:-1])
            venue = tokens[-1]
        elif len(tokens) >= 2:
            home_team = tokens[0]
            away_team = " ".join(tokens[1:])
            venue = ""
        else:
            home_team = col_parts[0]
            away_team = ""
            venue = ""

    home_team = normalize_team_name(home_team)
    away_team = normalize_team_name(away_team)
    venue = normalize_venue_name(venue)

    # Parsear árbitros y observaciones
    after_time_clean = re.sub(r"(\([A-Za-z0-9]\))([A-Za-z])", r"\1   \2", after_time)
    after_parts = [p.strip() for p in re.split(r"\s{2,}|\t", after_time_clean) if p.strip()]
    ref1 = ""
    ref2 = ""
    obs = ""

    if len(after_parts) == 1:
        if any(w in after_parts[0].lower() for w in OBSERVATION_KEYWORDS) or len(after_parts[0].split()) > 2:
            obs = after_parts[0]
        else:
            ref1 = after_parts[0]
    elif len(after_parts) == 2:
        if any(w in after_parts[0].lower() for w in OBSERVATION_KEYWORDS):
            obs = " ".join(after_parts)
        else:
            ref1 = after_parts[0]
            if any(w in after_parts[1].lower() for w in OBSERVATION_KEYWORDS) or len(after_parts[1].split()) > 2:
                obs = after_parts[1]
            else:
                ref2 = after_parts[1]
    elif len(after_parts) >= 3:
        ref1 = after_parts[0]
        ref2 = after_parts[1]
        obs = " ".join(after_parts[2:])

    is_sitas = is_sitas_team(home_team) or is_sitas_team(away_team)

    return {
        "division": current_division,
        "round_num": round_val,
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

    file_type = "pdf"
    if pdf_bytes.startswith(b"\x89PNG"):
        file_type = "png"
    elif pdf_bytes.startswith(b"\xff\xd8\xff"):
        file_type = "jpeg"
    elif pdf_bytes.startswith(b"RIFF") and b"WEBP" in pdf_bytes[:16]:
        file_type = "webp"

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype=file_type)
    except Exception:
        doc = pymupdf.open(stream=pdf_bytes)
    matches: List[Dict[str, Any]] = []
    current_division = "MENORES"

    for page in doc:
        pix = page.get_pixmap(dpi=200)
        res, _ = _ocr_engine(pix.tobytes("png"))
        if not res:
            continue

        items = []
        for box, text, _score in res:
            t = text.strip()
            # Separar textos pegados a fechas u horarios por artefactos del OCR
            t = re.sub(r"([A-Za-z])(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", r"\1   \2", t)
            t = re.sub(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})([A-Za-z])", r"\1   \2", t)
            t = re.sub(r"([A-Za-z])(\d{1,2}:\d{2})", r"\1   \2", t)
            t = re.sub(r"(\d{1,2}:\d{2})([A-Za-z])", r"\1   \2", t)
            y_center = (box[0][1] + box[2][1]) / 2
            x_left = box[0][0]
            items.append((y_center, x_left, t))
        items.sort(key=lambda item: item[0])

        lines = []
        curr_line = []
        curr_y = None
        for y, x, text in items:
            if curr_y is None or abs(y - curr_y) < 8.5:
                curr_line.append((x, y, text))
                curr_y = sum(iy for _, iy, _ in curr_line) / len(curr_line)
            else:
                curr_line.sort(key=lambda it: it[0])
                lines.append("   ".join([t for _, _, t in curr_line]))
                curr_line = [(x, y, text)]
                curr_y = y
        if curr_line:
            curr_line.sort(key=lambda it: it[0])
            lines.append("   ".join([t for _, _, t in curr_line]))

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
    estándar o no encuentra partidos suficientes, conmuta automáticamente a extracción con OCR.
    """
    raw_bytes: bytes
    if isinstance(pdf_source, (str, Path)):
        raw_bytes = Path(pdf_source).read_bytes()
    elif isinstance(pdf_source, bytes):
        raw_bytes = pdf_source
    else:
        raw_bytes = pdf_source.read()

    # Si el archivo recibido es una imagen (PNG, JPG, WEBP), procesar directamente con OCR
    if raw_bytes.startswith((b"\x89PNG", b"\xff\xd8\xff", b"RIFF")):
        return parse_schedule_with_ocr(raw_bytes)

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

    # 2. Si no se encontraron partidos con el texto nativo (por fuentes Type3 / imágenes)
    # o si se extrajeron muy pocos por fuentes incompletas, recurrir al OCR
    if _ocr_engine and (not matches or len(matches) < 8):
        ocr_matches = parse_schedule_with_ocr(raw_bytes)
        if len(ocr_matches) > len(matches):
            matches = ocr_matches

    return matches
