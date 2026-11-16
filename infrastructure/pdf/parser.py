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
    "SUB10", "SUB 10", "5UB10", "5UB 10",
    "SUB12", "SUB 12", "5UB12", "5UB 12",
    "SUB14 FLEX", "SUB 14 FLEX", "5UB14 FLEX", "5UB 14 FLEX",
    "SUB14", "SUB 14", "5UB14", "5UB 14",
    "SUB17 FLEX", "SUB 17 FLEX", "5UB17 FLEX", "5UB 17 FLEX",
    "SUB17", "SUB 17", "5UB17", "5UB 17",
    "SUB20", "SUB 20", "5UB20", "5UB 20",
    "PRIMERA A", "PRIMERA B", "PRIMERAA", "PRIMERAB",
    "PRIMERA MASCULINO", "MASCULINO", "MASCUUNO", "MASCULUINO",
    "MAXI 30", "MAXI30", "MAX1 30", "MAX130",
    "MAXI 35", "MAXI35", "MAX1 35", "MAX135",
    "MAXI 40", "MAXI40", "MAX1 40", "MAX140",
]

OBSERVATION_KEYWORDS = [
    "por", "si gana", "si ana", "gana", "bonaerenses", "reprogramado", "reprograma", "reprcgrama",
    "postergado", "cede", "cancha", "local", "sede", "presenta", "no se presenta", "jugadoras",
    "judío", "judio", "dia", "perdon", "torneo", "partido", "semana", "tienen que", "aviso", "susp",
    "invertimos", "cambiamos", "horarios", "disponibilidad", "esperar", "lleguen", "localia"
]


def normalize_category(cat: str) -> str:
    cat = cat.upper().strip()
    cat = re.sub(r"\b5UB\b", "SUB", cat)
    cat = re.sub(r"\b5UB(\d+)", r"SUB \1", cat)
    cat = re.sub(r"\bSUB(\d+)", r"SUB \1", cat)
    cat = re.sub(r"\bMAX[I1L](\d+)", r"MAXI \1", cat)
    cat = re.sub(r"\bMAX[I1L]\s+(\d+)", r"MAXI \1", cat)
    if "MASCUUNO" in cat or "MASCULUINO" in cat or cat == "MASCULINO":
        cat = "PRIMERA MASCULINO"
    elif cat == "PRIMERAA":
        cat = "PRIMERA A"
    elif cat == "PRIMERAB":
        cat = "PRIMERA B"
    cat = re.sub(r"\bSUB\s+(\d+)\s*FLEX\b", r"SUB \1 FLEX", cat)
    return re.sub(r"\s+", " ", cat)


def normalize_team_name(name: str) -> str:
    name = name.strip()
    if not name:
        return ""

    # Corrección de errores OCR típicos para SITAS
    name = re.sub(r"\bSITA5\b", "SITAS", name, flags=re.IGNORECASE)
    name = re.sub(r"\bSITAS\s+8\b", "SITAS B", name, flags=re.IGNORECASE)
    name = re.sub(r"\bseS\b", "SITAS", name)
    name = re.sub(r"^sitas$", "SITAS", name, flags=re.IGNORECASE)
    name = re.sub(r"^sitas\s+([a-z])$", lambda m: f"SITAS {m.group(1).upper()}", name, flags=re.IGNORECASE)
    name = re.sub(r"^sitas\s+flex$", "SITAS FLEX", name, flags=re.IGNORECASE)

    # Typo Ciudad (Cludad, CIudad, Cudad, Cuidad, CIUDAD)
    name = re.sub(r"\b(Cludad|CIudad|Cudad|Cuidad|Ciudsd|Ciudod|CIUDAD|ciudad)\b", "Ciudad", name, flags=re.IGNORECASE)
    name = re.sub(r"^Ciudad\s+([a-z])$", lambda m: f"Ciudad {m.group(1).upper()}", name, flags=re.IGNORECASE)

    # Typo Velez
    name = re.sub(r"^(zapan|za|Veiez|Vele2|V[eé]lez)$", "Velez", name, flags=re.IGNORECASE)
    name = re.sub(r"^g\s*zaa$", "Velez B", name, flags=re.IGNORECASE)
    name = re.sub(r"^v[eé]lez\s+([a-z])$", lambda m: f"Velez {m.group(1).upper()}", name, flags=re.IGNORECASE)

    # Typo Ballester
    name = re.sub(r"\b(Ballesier|Ballster|Bslester|Bellester|Blleter|Balester|BALLESTER)\b", "Ballester", name, flags=re.IGNORECASE)

    # Typo Hernandez
    name = re.sub(r"\b(Hernindez|Hemandez|Hermindez|Hern[aá]ndez|HERNANDEZ)\b", "Hernandez", name, flags=re.IGNORECASE)

    # Typo Social Parque
    name = re.sub(r"\b(5ocial\s+Parque|Social\s+Prque|Socisl\s+Parque|SOCIAL\s+PARQUE)\b", "Social Parque", name, flags=re.IGNORECASE)

    # Typo Hacoaj (Hacoa], Hacoal, Hacoai, Hecoaj, HACOAJ, HACOAI)
    name = re.sub(r"(?i)\b(?:Hacoa[\]jli1I]?|Hecoaj|HACOAJ|HACOAI|HACOAL)(?=\s|$)", "Hacoaj", name)
    name = re.sub(r"^Hacoaj\s+([a-z])$", lambda m: f"Hacoaj {m.group(1).upper()}", name, flags=re.IGNORECASE)

    # Typo Avellaneda
    name = re.sub(r"\b(AVELLANEDA|Avellaneds|Avelaneda)\b", "Avellaneda", name, flags=re.IGNORECASE)

    # Typo GEVP
    name = re.sub(r"^dA39$", "GEVP", name, flags=re.IGNORECASE)
    name = re.sub(r"^gevp$", "GEVP", name, flags=re.IGNORECASE)
    name = re.sub(r"^gevp\s+([a-z])$", lambda m: f"GEVP {m.group(1).upper()}", name, flags=re.IGNORECASE)

    name = re.sub(r"3[\*\"#']\s*vs\s*6[\*\"#']", "3° vs 6°", name, flags=re.IGNORECASE)
    name = re.sub(r"3[\*\"#']\s*al\s*6[\*\"#']", "3° al 6°", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip()


def normalize_venue_name(name: str) -> str:
    name = name.strip()
    if re.search(r"^(SITAS|SITA5|Sitas|sitas)$", name, flags=re.IGNORECASE):
        return "SITAS"
    if re.search(r"^(VELEZ|Velez|Veiez|Vele2|zapan|za)$", name, flags=re.IGNORECASE):
        return "VELEZ"
    if re.search(r"^(BALLESTER|Ballester|Ballesier|BALESTER)$", name, flags=re.IGNORECASE):
        return "BALLESTER"
    if re.search(r"^(AVELLANEDA|Avellaneda)$", name, flags=re.IGNORECASE):
        return "AVELLANEDA"
    if re.search(r"^(CIUDAD|Ciudad|Cludad|CIudad|Cudad|Cuidad)$", name, flags=re.IGNORECASE):
        return "CIUDAD"
    if re.search(r"^(HACOAJ|HACOAI|HACOAL|Hacoaj|Hacoal|Hacoa\]?)$", name, flags=re.IGNORECASE):
        return "HACOAJ"
    if re.search(r"^(GEVP|Gevp)$", name, flags=re.IGNORECASE):
        return "GEVP"
    if re.search(r"^(SOCIAL\s+PARQUE|5OCIAL\s+PARQUE|5ocial\s+Parque|Social\s+Parque)$", name, flags=re.IGNORECASE):
        return "SOCIAL PARQUE"
    if re.search(r"^(APV|Apv)$", name, flags=re.IGNORECASE):
        return "APV"
    return name


def normalize_round_name(round_raw: str) -> Union[int, str]:
    """Normaliza la columna FECHA # / instancia (ej. Copa Oro - Final Ida, 3° Puesto Ida, Puesto del 5° al 10°)."""
    s = re.sub(r"^FECHA\s*#?\s*", "", round_raw, flags=re.IGNORECASE).strip()
    if not s:
        return ""
    if s.isdigit():
        return int(s)

    # Correcciones de Copa Oro / Plata / Bronce
    s = re.sub(r"\b(Cope|Cap[ao])\b", "Copa", s, flags=re.IGNORECASE)
    s = re.sub(r"\bCopa\s+(?:de\s+)?(Cro|Ono|0ro|Qro|Dra|Dro|Ore|Opo|Oro)\b", "Copa Oro", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(Cro|Ono|0ro|Qro)\b", "Oro", s, flags=re.IGNORECASE)
    s = re.sub(r"\bCopa\s+de\s+(Oro|Plata|Bronce)\b", lambda m: f"Copa {m.group(1).capitalize()}", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(Piata|P1ata|Plala|Plata)\b", "Plata", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(8ronce|Brcnce|Bronce)\b", "Bronce", s, flags=re.IGNORECASE)

    # Correcciones de Puesto / Partido / Final / Semifinal / Ida / Vuelta
    s = re.sub(r"\b(Pueslo|Punsto|Pucsto|Puetso|Puosto|Puesto)\b", "Puesto", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(Parlido|Partldo|Partdo|Partido)\b", "Partido", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(Semifial|Seminal|Semifinal)\b", "Semifinal", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(Fina1|Flna1|Flnal|Final)\b", "Final", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(Iida|lIda|Ilda|1da|lda|ida|Ida)\b", "Ida", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(Vue1ta|Vuetta|vuelta|Vuelta)\b", "Vuelta", s, flags=re.IGNORECASE)
    s = re.sub(r"\bAmistos[0o]\b", "Amistoso", s, flags=re.IGNORECASE)

    # Ordinales antes de Puesto o Partido (ej. 39 Puesto -> 3° Puesto, 5# Puesto -> 5° Puesto, 72 Puesto -> 7° Puesto)
    s = re.sub(r"(?<!\d)(1[0-5])[9f#\+′'*°º\"ª]?\s*(?=Puesto|Partido)", r"\1° ", s, flags=re.IGNORECASE)
    s = re.sub(r"(?<!\d)1[9#\+′'*°º\"ª]?\s*(?=Puesto|Partido)", "1° ", s, flags=re.IGNORECASE)
    s = re.sub(r"(?<!\d)([2-9])[029#\+′'*°º\"ª]?\s*(?=Puesto|Partido)", r"\1° ", s, flags=re.IGNORECASE)

    # Expresiones "Puesto del X° al Y°" o "X° al Y° Puesto"
    s = re.sub(r"(\d[^\s]*)\s*a[1lI]\s*(\d)", r"\1 al \2", s, flags=re.IGNORECASE)
    s = re.sub(
        r"Puesto\s+del\s+(\d{1,2})[09f#\+′'*°º\"ªe]?\s*al\s*(\d{1,2})[09f#\+′'*°º\"ª]?",
        lambda m: f"Puesto del {5 if m.group(1) in ('50', '59') else int(m.group(1))}° al {10 if m.group(2) in ('10', '0') else (9 if m.group(2) == '99' else int(m.group(2)))}°",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"(?<!del\s)\b(\d{1,2})[09f#\+′'*°º\"ªe]?\s*al\s*(\d{1,2})[09f#\+′'*°º\"ª]?\s*Puesto",
        lambda m: f"{5 if m.group(1) in ('50', '59') else int(m.group(1))}° al {10 if m.group(2) in ('10', '0') else int(m.group(2))}° Puesto",
        s,
        flags=re.IGNORECASE,
    )

    # Asegurar guión con espacios en "Copa Oro - Final Ida", etc.
    s = re.sub(r"\s*-\s*", " - ", s)
    s = re.sub(r"\b(Copa\s+(?:Oro|Plata|Bronce))\s+(?!-)(Final|Semifinal|Cuartos|\d+°)", r"\1 - \2", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_observation(obs: str) -> str:
    """Corrige errores típicos de OCR en la columna de Observaciones."""
    obs = obs.strip()
    if not obs:
        return ""
    obs = re.sub(r"\b(Cludad|CIudad|Cudad|Cuidad)\b", "Ciudad", obs, flags=re.IGNORECASE)
    obs = re.sub(r"\bSi\s+ana\b", "Si gana", obs, flags=re.IGNORECASE)
    obs = re.sub(r"\bsabedo\b", "sábado", obs, flags=re.IGNORECASE)
    obs = re.sub(r"\breprcgrama\b", "reprograma", obs, flags=re.IGNORECASE)
    obs = re.sub(r"\bllgan\s+la\s+jugadoras\b", "llegan las jugadoras", obs, flags=re.IGNORECASE)
    obs = re.sub(r"\bllgan\b", "llegan", obs, flags=re.IGNORECASE)
    obs = re.sub(r"\bHacoa\]", "Hacoaj", obs, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", obs).strip()


def is_sitas_team(team_name: str) -> bool:
    """Verifica si el nombre del equipo corresponde a SITAS en cualquiera de sus variantes."""
    if not team_name:
        return False
    # Detecta SITAS, Sitas, sitas, SITAS B, SITAS FLEX, SITA5 (OCR typo), seS, S.I.T.A.S.
    return bool(re.search(r"\b(S\.?I\.?T\.?A\.?S\.?|SITA5|seS)\b", team_name, re.IGNORECASE))


def normalize_referee_name(name: str) -> str:
    """Estandariza nombres de árbitros y corrige artefactos OCR en credenciales (ej. (8) -> (B))."""
    name = name.strip()
    if not name:
        return ""
    if name.lower() in ("n/a", "na", "-"):
        return "n/a"
    name = re.sub(r"[\[\{]([A-Za-z0-9\u03b2])[\]\}]", r"(\1)", name)
    name = re.sub(r"[\[\{]([A-Za-z0-9\u03b2])\)", r"(\1)", name)
    name = re.sub(r"\(([A-Za-z0-9\u03b2])[\]\}]", r"(\1)", name)
    name = re.sub(r"\([8b\u03b2]\)", "(B)", name)
    name = re.sub(r"([A-Za-z])\(([A-Za-z0-9])\)", r"\1 (\2)", name)
    name = re.sub(r"\bArg[0Gcg]ello\b", "Arguello", name, flags=re.IGNORECASE)
    name = re.sub(r"\bLonatz\b", "Lofiatz", name, flags=re.IGNORECASE)
    name = re.sub(r"\bLoniatz\b", "Lofiatz", name, flags=re.IGNORECASE)
    name = re.sub(r"\bLoriatz\b", "Lofiatz", name, flags=re.IGNORECASE)
    name = re.sub(r"\bLofatz\b", "Lofiatz", name, flags=re.IGNORECASE)
    name = re.sub(r"\bEmile\b", "Emilce", name, flags=re.IGNORECASE)
    name = re.sub(r"\bEmiloe\b", "Emilce", name, flags=re.IGNORECASE)
    name = re.sub(r"\bNoma\b", "Norma", name, flags=re.IGNORECASE)
    name = re.sub(r"\bTurr[li]?\b", "Turri", name, flags=re.IGNORECASE)
    name = re.sub(r"\bTrr\b", "Turri", name, flags=re.IGNORECASE)
    name = re.sub(r"\bL6pez\b", "Lopez", name, flags=re.IGNORECASE)
    name = re.sub(r"\bMunguie\b", "Munguia", name, flags=re.IGNORECASE)
    name = re.sub(r"\branzo\b", "Iranzo", name, flags=re.IGNORECASE)
    name = re.sub(r"\bIA\]", "(A)", name)
    name = re.sub(r"\b18\)", "(B)", name)
    return re.sub(r"\s+", " ", name).strip()


def is_referee_token(t: str) -> bool:
    """Verifica si un token corresponde a un árbitro (por credencial o nombre de persona)."""
    t = t.strip()
    if not t:
        return False
    if t.lower() in ("n/a", "na", "-"):
        return True
    if re.search(r"[\(\[\{][A-Za-z0-9\u03b2][\)\]\}]", t):
        return True
    if any(w in t.lower() for w in OBSERVATION_KEYWORDS):
        return False
    words = t.split()
    if 1 <= len(words) <= 3 and not re.search(r"\d", t):
        return True
    return False


def is_observation_token(t: str) -> bool:
    """Verifica si un fragmento corresponde a observaciones del partido."""
    t = t.strip()
    if not t:
        return False
    if any(w in t.lower() for w in OBSERVATION_KEYWORDS):
        return True
    if len(t.split()) > 3 and not re.search(r"[\(\[\{][A-Za-z0-9\u03b2][\)\]\}]\s*$", t):
        return True
    return False


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
    date_match = re.search(r"((?<!\d)\d{1,2}[/-]\d{1,2}[/-]\d{2,4}(?!\d))", line)
    if not date_match:
        return None

    round_raw = line[:date_match.start()].strip()
    round_val = normalize_round_name(round_raw)

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

    known_venues_upper = {"AVELLANEDA", "BALLESTER", "CIUDAD", "VELEZ", "SITAS", "HACOAJ", "GEVP", "LANUS", "SOCIAL PARQUE", "APV"}

    if len(col_parts) >= 3:
        home_team = col_parts[0]
        away_team = col_parts[1]
        venue = " ".join(col_parts[2:])
    elif len(col_parts) == 2:
        if col_parts[1].upper() in known_venues_upper:
            venue = col_parts[1].upper()
            if venue == "AVELLANEDA" and "avellaneda" not in col_parts[0].lower():
                home_team = "Avellaneda"
                away_team = col_parts[0]
            else:
                home_team = col_parts[0]
                away_team = ""
        else:
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
    after_time_clean = re.sub(r"(\([A-Za-z0-9\u03b2]\))([A-Za-z])", r"\1   \2", after_time)
    after_parts = [p.strip() for p in re.split(r"\s{2,}|\t", after_time_clean) if p.strip()]
    ref1 = ""
    ref2 = ""
    obs = ""

    if len(after_parts) == 1:
        p0 = after_parts[0]
        if is_observation_token(p0) and not is_referee_token(p0):
            obs = p0
        else:
            ref1 = normalize_referee_name(p0)
            if ref1 == "n/a":
                ref2 = "n/a"
    elif len(after_parts) == 2:
        p0, p1 = after_parts[0], after_parts[1]
        if is_observation_token(p0) and not is_referee_token(p0):
            obs = f"{p0} {p1}"
        elif is_observation_token(p1) and not is_referee_token(p1):
            ref1 = normalize_referee_name(p0)
            obs = p1
        else:
            ref1 = normalize_referee_name(p0)
            ref2 = normalize_referee_name(p1)
    elif len(after_parts) >= 3:
        ref1 = normalize_referee_name(after_parts[0])
        ref2 = normalize_referee_name(after_parts[1])
        obs = " ".join(after_parts[2:])

    obs = normalize_observation(obs)
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


def _harmonize_dates(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Corrige errores de OCR donde un mes de dos dígitos pierde un dígito
    (ej. '14/1/2026' -> '14/01/2026' cuando todo el cronograma es de '11/2026').
    """
    if len(matches) < 3:
        return matches

    from collections import Counter
    month_year_counts: Counter[tuple[str, str]] = Counter()
    for m in matches:
        d = (m.get("match_date") or "").split("/")
        if len(d) == 3:
            month_year_counts[(d[1], d[2])] += 1

    if not month_year_counts:
        return matches

    (dom_month, dom_year), dom_count = month_year_counts.most_common(1)[0]
    if dom_count < len(matches) * 0.6:
        return matches

    for m in matches:
        d = (m.get("match_date") or "").split("/")
        if len(d) == 3:
            day, month, year = d
            if year == dom_year and month != dom_month:
                # Si el mes dominante es 10, 11 o 12 y el OCR leyó 01 o 02 (por pérdida de un '1')
                if dom_month in ("10", "11", "12") and month in ("01", "02"):
                    m["match_date"] = f"{day}/{dom_month}/{year}"
    return matches


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
    ocr_pages: List[tuple[int, int, List[Any]]] = []
    current_division = "MENORES"

    for page in doc:
        # Usamos 300 DPI para óptima detección de texto en celdas con fondos resaltados
        pix = page.get_pixmap(dpi=300)
        res, _ = _ocr_engine(pix.tobytes("png"))
        if not res:
            continue
        ocr_pages.append((pix.width, pix.height, res))

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

        line_thresh = 13.0
        lines = []
        curr_line = []
        curr_y = None
        for y, x, text in items:
            if curr_y is None or abs(y - curr_y) < line_thresh:
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

        # Si el formato de Capital Federal no arrojó partidos pero la página actual es de Fase de Grupos Nacional,
        # parsear directamente y evitar OCR innecesario en hojas posteriores de playoffs/cuadros.
        if not matches and ocr_pages:
            national_matches = _parse_national_schedule_from_ocr_pages(ocr_pages)
            if len(national_matches) >= 8:
                return national_matches

    if not matches and ocr_pages:
        national_matches = _parse_national_schedule_from_ocr_pages(ocr_pages)
        if national_matches:
            return national_matches

    return _harmonize_dates(matches)


def _normalize_national_team_name(name: str) -> str:
    """Normaliza nombres de clubes en fixtures de competencias nacionales (Liga Federal / Ligas Nacionales)."""
    s = re.sub(r"\s+", " ", name).strip()
    if not s:
        return ""
    mapping = {
        "CENTRALCORDOBA": "Central Córdoba",
        "CENTRAL CORDOBA": "Central Córdoba",
        "CENTRAL CÓRDOBA": "Central Córdoba",
        "HERCULES": "Hércules",
        "HÉRCULES": "Hércules",
        "LEONAS": "Leonas",
        "SITAS": "SITAS",
        "C.A.NAZARENO": "C.A. Nazareno",
        "C.A. NAZARENO": "C.A. Nazareno",
        "BOLIVAR": "Bolívar",
        "BOLÍVAR": "Bolívar",
        "VELEZ": "Vélez",
        "VÉLEZ": "Vélez",
        "BELGRANO": "Belgrano",
        "COLON": "Colón",
        "COLÓN": "Colón",
        "JAIMEZAPATA": "Jaime Zapata",
        "JAIME ZAPATA": "Jaime Zapata",
        "DEFENSORESD.S.": "Defensores D.S.",
        "DEFENSORES D.S.": "Defensores D.S.",
        "ESTUDIANTES": "Estudiantes",
        "LUZYFUERZA": "Luz y Fuerza",
        "LUZ Y FUERZA": "Luz y Fuerza",
        "LIBERTAD": "Libertad",
        "SOCIALPARQUE": "Social Parque",
        "SOCIAL PARQUE": "Social Parque",
        "DEPORTIVOCUYO": "Deportivo Cuyo",
        "DEPORTIVO CUYO": "Deportivo Cuyo",
    }
    upper = s.upper()
    if upper in mapping:
        return mapping[upper]
    return normalize_team_name(s)


def _normalize_national_venue_name(venue_raw: str) -> str:
    """Normaliza nombres de canchas/sedes en fixtures nacionales."""
    v = re.sub(r"\s+", " ", venue_raw).strip().upper()
    if "JAIME" in v or "ZAPATA" in v:
        return "Polideportivo Jaime Zapata"
    if "CUNE" in v:
        return "Club CUNE"
    if "CPCE" in v:
        return "Predio Social CPCE"
    return venue_raw.strip()


def _parse_national_schedule_from_ocr_pages(
    ocr_pages: List[tuple[int, int, List[Any]]],
    default_year: str = "2026",
) -> List[Dict[str, Any]]:
    """
    Parsea exclusivamente los partidos de Fase de Grupos en fixtures de Competencias Nacionales
    (como Liga Federal / Liga Nacional de la Confederación Argentina de Cestoball)
    cuando el formato estándar de Capital Federal no aplica.
    """
    if not ocr_pages:
        return []

    all_texts_upper = " ".join(
        t.upper()
        for _w, _h, res in ocr_pages
        for _box, t, _score in (res or [])
    )

    if "GRUPO" not in all_texts_upper or "PARTIDO" not in all_texts_upper:
        return []

    tournament_cat = "LIGA FEDERAL"
    if "LIGANACIONAL" in all_texts_upper or "LIGA NACIONAL" in all_texts_upper:
        if "SUB17" in all_texts_upper or "SUB 17" in all_texts_upper:
            tournament_cat = "LIGA NACIONAL SUB 17"
        elif "SUB14" in all_texts_upper or "SUB 14" in all_texts_upper:
            tournament_cat = "LIGA NACIONAL SUB 14"
        elif "MASC" in all_texts_upper:
            tournament_cat = "LIGA NACIONAL MASCULINA"
        else:
            tournament_cat = "LIGA NACIONAL"
    elif "ARGENTINO" in all_texts_upper:
        tournament_cat = "CAMPEONATO ARGENTINO"

    day_pattern = r"(LUNES|MARTES|MI[EÉ]RCOLES|JUEVES|VIERNES|S[AÁ]BADO|DOMINGO)"
    group_line_re = re.compile(
        r"GRUPO\s*([A-Z])\s*[-–]\s*Fecha\s*(\d+)\s*[-–]\s*Partido\s*(\d+)",
        re.IGNORECASE,
    )
    header_dt_re = re.compile(
        rf"^{day_pattern}\s*(?:(\d{{1,2}}/\d{{2}}))?\s*(\d{{1,2}}[\.:]\d{{2}})\s*h[sS]?\s*(.+)$",
        re.IGNORECASE,
    )

    matches: List[Dict[str, Any]] = []

    for page_w, _page_h, res in ocr_pages:
        if not res:
            continue

        day_to_date: Dict[str, str] = {}
        for _box, text, _score in res:
            m_dt = header_dt_re.match(text.strip())
            if m_dt and m_dt.group(2):
                day_key = m_dt.group(1).upper()
                day_to_date[day_key] = m_dt.group(2)

        mid_x = page_w / 2.0
        columns: List[List[tuple[float, float, float, float, str]]] = [[], []]

        for box, text, _score in res:
            t = text.strip()
            if not t:
                continue
            x1, y1 = float(box[0][0]), float(box[0][1])
            x2, y2 = float(box[2][0]), float(box[2][1])
            x_center = (x1 + x2) / 2.0
            y_center = (y1 + y2) / 2.0
            col_idx = 0 if x_center < mid_x else 1
            columns[col_idx].append((y_center, x_center, x1, x2, t))

        for col_items in columns:
            col_items.sort(key=lambda it: it[0])

            for idx, (y_grp, _x_grp, _x1, _x2, text_grp) in enumerate(col_items):
                m_grp = group_line_re.search(text_grp)
                if not m_grp:
                    continue

                grp_letter = m_grp.group(1).upper()
                fecha_num = m_grp.group(2)
                partido_num = m_grp.group(3)

                match_date = ""
                time_str = "-"
                venue = ""
                for prev_idx in range(idx - 1, -1, -1):
                    y_prev, _, _, _, t_prev = col_items[prev_idx]
                    if y_grp - y_prev > 110:
                        break
                    m_dt = header_dt_re.match(t_prev)
                    if m_dt:
                        day_key = m_dt.group(1).upper()
                        dd_mm = m_dt.group(2) or day_to_date.get(day_key, "")
                        if dd_mm:
                            d_parts = dd_mm.split("/")
                            match_date = f"{d_parts[0].zfill(2)}/{d_parts[1].zfill(2)}/{default_year}"
                        raw_time = m_dt.group(3).replace(".", ":")
                        t_parts = raw_time.split(":")
                        time_str = f"{int(t_parts[0]):02d}:{t_parts[1]}"
                        venue = _normalize_national_venue_name(m_dt.group(4))
                        break

                team_candidates: List[tuple[float, str]] = []
                for next_idx in range(idx + 1, len(col_items)):
                    y_next, x_next, _, _, t_next = col_items[next_idx]
                    dy = y_next - y_grp
                    if dy < 20:
                        continue
                    if dy > 125:
                        break
                    if group_line_re.search(t_next) or header_dt_re.match(t_next):
                        break
                    if "GRUPO" in t_next.upper() and "FECHA" in t_next.upper():
                        break
                    clean_tok = re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ\.]", "", t_next)
                    if len(clean_tok) < 2:
                        continue
                    team_candidates.append((x_next, t_next))

                if len(team_candidates) >= 2:
                    team_candidates.sort(key=lambda tc: tc[0])
                    home_team = _normalize_national_team_name(team_candidates[0][1])
                    away_team = _normalize_national_team_name(team_candidates[-1][1])
                else:
                    continue

                is_sitas = is_sitas_team(home_team) or is_sitas_team(away_team)
                matches.append({
                    "division": "MAYORES",
                    "round_num": f"Grupo {grp_letter} - Fecha {fecha_num}",
                    "match_date": match_date,
                    "time": time_str,
                    "category": tournament_cat,
                    "home_team": home_team,
                    "away_team": away_team,
                    "venue": venue,
                    "ref1": "",
                    "ref2": "",
                    "observations": f"Partido {partido_num}",
                    "is_sitas": is_sitas,
                })

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

    return _harmonize_dates(matches)
