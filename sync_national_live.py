"""
Sincronizador seguro (Server-Side / Build-Time) para Competencias Nacionales (Liga Federal).
Lee las credenciales de Firestore exclusivamente desde variables de entorno (.env local en gitignore
o GitHub Actions Encrypted Secrets) para que jamás se expongan API Keys ni IDs en el frontend público.
Actualiza web/upcoming.json únicamente con los resultados y cruces de playoffs de SITAS.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
UPCOMING_PATH = BASE_DIR / "web" / "upcoming.json"

# Cronograma oficial de Playoffs de la Liga Federal (Partidos 25 al 48 del PDF oficial)
LIGA_FEDERAL_PLAYOFF_SCHEDULE: Dict[int, Dict[str, str]] = {
    25: {"round_num": "Cuartos 9° al 16°", "match_date": "21/11/2026", "time": "09:00", "venue": "Polideportivo Jaime Zapata", "pLocal": "3°A", "pVis": "4°B"},
    26: {"round_num": "Cuartos 9° al 16°", "match_date": "21/11/2026", "time": "09:00", "venue": "Club CUNE", "pLocal": "3°C", "pVis": "4°D"},
    27: {"round_num": "Cuartos 9° al 16°", "match_date": "21/11/2026", "time": "10:30", "venue": "Polideportivo Jaime Zapata", "pLocal": "3°B", "pVis": "4°A"},
    28: {"round_num": "Cuartos 9° al 16°", "match_date": "21/11/2026", "time": "10:30", "venue": "Club CUNE", "pLocal": "3°D", "pVis": "4°C"},
    29: {"round_num": "Cuartos 1° al 8°", "match_date": "21/11/2026", "time": "18:00", "venue": "Polideportivo Jaime Zapata", "pLocal": "1°A", "pVis": "2°B"},
    30: {"round_num": "Cuartos 1° al 8°", "match_date": "21/11/2026", "time": "18:00", "venue": "Club CUNE", "pLocal": "1°C", "pVis": "2°D"},
    31: {"round_num": "Cuartos 1° al 8°", "match_date": "21/11/2026", "time": "19:30", "venue": "Polideportivo Jaime Zapata", "pLocal": "1°B", "pVis": "2°A"},
    32: {"round_num": "Cuartos 1° al 8°", "match_date": "21/11/2026", "time": "19:30", "venue": "Club CUNE", "pLocal": "1°D", "pVis": "2°C"},
    33: {"round_num": "Semifinal 13° al 16°", "match_date": "22/11/2026", "time": "08:00", "venue": "Polideportivo Jaime Zapata", "pLocal": "P25", "pVis": "P26"},
    34: {"round_num": "Semifinal 13° al 16°", "match_date": "22/11/2026", "time": "08:00", "venue": "Club CUNE", "pLocal": "P27", "pVis": "P28"},
    35: {"round_num": "Semifinal 9° al 12°", "match_date": "22/11/2026", "time": "09:30", "venue": "Polideportivo Jaime Zapata", "pLocal": "G25", "pVis": "G26"},
    36: {"round_num": "Semifinal 9° al 12°", "match_date": "22/11/2026", "time": "09:30", "venue": "Club CUNE", "pLocal": "G27", "pVis": "G28"},
    37: {"round_num": "Semifinal 5° al 8°", "match_date": "22/11/2026", "time": "11:00", "venue": "Club CUNE", "pLocal": "P29", "pVis": "P30"},
    38: {"round_num": "Semifinal 5° al 8°", "match_date": "22/11/2026", "time": "12:30", "venue": "Club CUNE", "pLocal": "P31", "pVis": "P32"},
    39: {"round_num": "Semifinal 1° al 4°", "match_date": "22/11/2026", "time": "11:00", "venue": "Polideportivo Jaime Zapata", "pLocal": "G29", "pVis": "G30"},
    40: {"round_num": "Semifinal 1° al 4°", "match_date": "22/11/2026", "time": "12:30", "venue": "Polideportivo Jaime Zapata", "pLocal": "G31", "pVis": "G32"},
    41: {"round_num": "15° Puesto", "match_date": "22/11/2026", "time": "17:15", "venue": "Club CUNE", "pLocal": "P33", "pVis": "P34"},
    42: {"round_num": "13° Puesto", "match_date": "22/11/2026", "time": "18:45", "venue": "Club CUNE", "pLocal": "G33", "pVis": "G34"},
    43: {"round_num": "11° Puesto", "match_date": "22/11/2026", "time": "20:15", "venue": "Club CUNE", "pLocal": "P35", "pVis": "P36"},
    44: {"round_num": "9° Puesto", "match_date": "22/11/2026", "time": "17:15", "venue": "Polideportivo Jaime Zapata", "pLocal": "G35", "pVis": "G36"},
    45: {"round_num": "7° Puesto", "match_date": "22/11/2026", "time": "18:45", "venue": "Polideportivo Jaime Zapata", "pLocal": "P37", "pVis": "P38"},
    46: {"round_num": "5° Puesto", "match_date": "22/11/2026", "time": "20:15", "venue": "Polideportivo Jaime Zapata", "pLocal": "G37", "pVis": "G38"},
    47: {"round_num": "3° Puesto", "match_date": "23/11/2026", "time": "09:00", "venue": "Polideportivo Jaime Zapata", "pLocal": "P39", "pVis": "P40"},
    48: {"round_num": "Final", "match_date": "23/11/2026", "time": "11:00", "venue": "Polideportivo Jaime Zapata", "pLocal": "G39", "pVis": "G40"},
}


def _load_env_file() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def _parse_firestore_val(val: Any) -> Any:
    if not isinstance(val, dict):
        return None
    if "stringValue" in val:
        return val["stringValue"]
    if "integerValue" in val:
        return int(val["integerValue"])
    if "doubleValue" in val:
        return float(val["doubleValue"])
    if "booleanValue" in val:
        return bool(val["booleanValue"])
    if "nullValue" in val:
        return None
    if "timestampValue" in val:
        return val["timestampValue"]
    if "arrayValue" in val:
        return [_parse_firestore_val(v) for v in val["arrayValue"].get("values", [])]
    if "mapValue" in val:
        fields = val["mapValue"].get("fields", {})
        return {k: _parse_firestore_val(v) for k, v in fields.items()}
    return None


def _parse_firestore_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    name = doc.get("name", "")
    doc_id = name.rsplit("/", 1)[-1]
    out: Dict[str, Any] = {"id": doc_id}
    for k, v in (doc.get("fields") or {}).items():
        out[k] = _parse_firestore_val(v)
    return out


def _fetch_collection(project_id: str, db_id: str, api_key: str, subpath: str, page_size: int = 250) -> List[Dict[str, Any]]:
    url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/{db_id}/documents/{subpath}?pageSize={page_size}"
    if api_key:
        url += f"&key={api_key}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [_parse_firestore_doc(d) for d in data.get("documents", []) if d.get("name")]


def _extract_match_num(p: Dict[str, Any]) -> int | None:
    fase = str(p.get("fase") or "")
    if fase:
        m = re.search(r"(?:partido|p\.|p|#)\s*(\d+)", fase, re.IGNORECASE) or re.search(r"-\s*(\d+)\s*$", fase)
        if m:
            return int(m.group(1))
    if isinstance(p.get("orden_playoff"), int) and p["orden_playoff"] > 0:
        return p["orden_playoff"]
    nro_fecha = str(p.get("nro_fecha") or "")
    if nro_fecha:
        m = re.search(r"(?:partido|p|#)\s*(\d+)", nro_fecha, re.IGNORECASE)
        if m:
            return int(m.group(1))
    if isinstance(p.get("orden"), int) and p["orden"] > 0:
        return p["orden"]
    return None


def _is_finished(p: Dict[str, Any]) -> bool:
    st = str(p.get("estado") or "").upper()
    pd = p.get("planilla_digital") or {}
    pd_st = str(pd.get("estadoPlanilla") or "").upper() if isinstance(pd, dict) else ""
    return st in ("FINALIZADO", "JUGADO") or pd_st in ("FINALIZADO", "FIRMADO")


def _is_live(p: Dict[str, Any]) -> bool:
    if _is_finished(p):
        return False
    st = str(p.get("estado") or "").upper()
    pd = p.get("planilla_digital") or {}
    pd_st = str(pd.get("estadoPlanilla") or "").upper() if isinstance(pd, dict) else ""
    return st == "EN_JUEGO" or pd_st == "EN_JUEGO"


def _get_scores(p: Dict[str, Any]) -> tuple[int | None, int | None]:
    pd = p.get("planilla_digital") if isinstance(p.get("planilla_digital"), dict) else {}
    gl = p.get("golesLocal") if p.get("golesLocal") is not None else pd.get("golesTotalLocal")
    gv = p.get("golesVisitante") if p.get("golesVisitante") is not None else pd.get("golesTotalVisitante")
    return (int(gl) if gl is not None else None, int(gv) if gv is not None else None)


def _format_date(raw_date: Any, fallback: str = "") -> str:
    if not raw_date or re.search(r"sin fecha", str(raw_date), re.IGNORECASE):
        return fallback
    s = str(raw_date).strip()
    m_iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m_iso:
        return f"{m_iso.group(3)}/{m_iso.group(2)}/{m_iso.group(1)}"
    m_short = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", s)
    if m_short:
        d = m_short.group(1).zfill(2)
        m = m_short.group(2).zfill(2)
        y = m_short.group(3) or "2026"
        if len(y) == 2:
            y = "20" + y
        return f"{d}/{m}/{y}"
    return s or fallback


def _format_time(raw_time: Any, fallback: str = "-") -> str:
    if not raw_time or re.search(r"sin hora", str(raw_time), re.IGNORECASE):
        return fallback
    s = re.sub(r"\s*hs\.?$", "", str(raw_time).strip(), flags=re.IGNORECASE).replace(".", ":")
    m = re.match(r"^(\d{1,2}):(\d{2})", s)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return s or fallback


def _resolve_venue(p: Dict[str, Any], fallback: str = "Por definir") -> str:
    ubic = str(p.get("ubicacion") or "").strip()
    if ubic and not re.search(r"por definir", ubic, re.IGNORECASE):
        return ubic
    c = str(p.get("cancha") or "").strip().upper()
    if c == "1" or "JAIME" in c or "ZAPATA" in c:
        return "Polideportivo Jaime Zapata"
    if c == "2" or "CUNE" in c:
        return "Club CUNE"
    if c == "3" or "CPCE" in c:
        return "Predio Social CPCE"
    return fallback


def sync_national_schedule_file(upcoming_path: Path = UPCOMING_PATH) -> bool:
    _load_env_file()
    project_id = os.environ.get("CESTO_FIRESTORE_PROJECT_ID", "").strip()
    db_id = os.environ.get("CESTO_FIRESTORE_DB_ID", "").strip()
    api_key = os.environ.get("CESTO_FIRESTORE_API_KEY", "").strip()
    torneo_id = os.environ.get("CESTO_TORNEO_ID", "").strip()

    if not project_id or not db_id or not torneo_id:
        return False

    if not upcoming_path.exists():
        return False

    data = json.loads(upcoming_path.read_text(encoding="utf-8"))
    all_matches: List[Dict[str, Any]] = data.get("matches", [])
    if not any(re.search(r"LIGA FEDERAL|LIGA NACIONAL|ARGENTINO", str(m.get("category") or ""), re.IGNORECASE) for m in all_matches):
        return False

    zonas = _fetch_collection(project_id, db_id, api_key, f"torneos/{torneo_id}/zonas", 50)
    partidos = _fetch_collection(project_id, db_id, api_key, f"torneos/{torneo_id}/partidos", 250)
    clubes_list = _fetch_collection(project_id, db_id, api_key, "clubes", 300)

    if not partidos:
        return False

    clubes_map: Dict[str, Dict[str, Any]] = {}
    sitas_ids: set[str] = set()
    for c in clubes_list:
        cid = c["id"]
        clubes_map[cid] = c
        for al in (c.get("alias") or []):
            if al:
                clubes_map[str(al)] = c
        if re.search(r"\b(s\.?i\.?t\.?a\.?s\.?|sita5)\b", str(c.get("nombre") or ""), re.IGNORECASE):
            sitas_ids.add(cid)
            for al in (c.get("alias") or []):
                if al:
                    sitas_ids.add(str(al))

    def is_club_sitas(club_obj: Dict[str, Any] | None, raw_name: str = "") -> bool:
        if club_obj and club_obj.get("id") in sitas_ids:
            return True
        name_check = (club_obj.get("nombre") if club_obj else None) or raw_name
        return bool(re.search(r"\b(s\.?i\.?t\.?a\.?s\.?|sita5)\b", str(name_check or ""), re.IGNORECASE))

    def calc_zone_standings(zona_id: str) -> List[Dict[str, Any]]:
        zona = next((z for z in zonas if z["id"] == zona_id), None)
        if not zona or not isinstance(zona.get("equiposIds"), list):
            return []
        z_matches = [p for p in partidos if not p.get("es_playoff") and p.get("zonaId") == zona_id and _is_finished(p)]
        stats_map: Dict[str, Dict[str, Any]] = {}
        unique_entries: List[Dict[str, Any]] = []
        for cid in zona["equiposIds"]:
            club = clubes_map.get(cid)
            canon_id = club["id"] if club else cid
            if canon_id not in stats_map:
                entry = {
                    "id": canon_id,
                    "nombre": club.get("nombre", cid) if club else cid,
                    "escudo_url": club.get("escudo_url") if club else None,
                    "pj": 0, "pg": 0, "pp": 0, "gf": 0, "gc": 0, "pts": 0, "dg": 0,
                }
                stats_map[canon_id] = entry
                unique_entries.append(entry)
            stats_map[cid] = stats_map[canon_id]

        for p in z_matches:
            loc = stats_map.get(p.get("equipoLocalId"))
            vis = stats_map.get(p.get("equipoVisitanteId"))
            if not loc or not vis:
                continue
            gl_raw, gv_raw = _get_scores(p)
            gl, gv = int(gl_raw or 0), int(gv_raw or 0)
            loc["pj"] += 1
            vis["pj"] += 1
            loc["gf"] += gl
            loc["gc"] += gv
            vis["gf"] += gv
            vis["gc"] += gl
            if gl > gv:
                loc["pg"] += 1
                loc["pts"] += 2
                vis["pp"] += 1
                vis["pts"] += 0 if p.get("walkoverLossId") == p.get("equipoVisitanteId") else 1
            else:
                vis["pg"] += 1
                vis["pts"] += 2
                loc["pp"] += 1
                loc["pts"] += 0 if p.get("walkoverLossId") == p.get("equipoLocalId") else 1

        for t in unique_entries:
            t["dg"] = t["gf"] - t["gc"]

        unique_entries.sort(key=lambda x: (x["pts"], x["dg"], x["gf"]), reverse=True)
        return unique_entries

    def is_zone_finished(zona_id: str) -> bool:
        z_matches = [p for p in partidos if not p.get("es_playoff") and p.get("zonaId") == zona_id]
        zona = next((z for z in zonas if z["id"] == zona_id), None)
        expected = 6 if (zona and len(zona.get("equiposIds") or []) >= 4) else 3
        return len(z_matches) >= expected and all(_is_finished(p) for p in z_matches)

    def find_zone_by_letter(letter: str) -> Dict[str, Any] | None:
        target = letter.upper()
        for z in zonas:
            n = str(z.get("nombre") or "").strip().upper()
            if n == target or re.search(rf"(?:ZONA|GRUPO)\s*{target}\b", n, re.IGNORECASE):
                return z
        return None

    def resolve_placeholder(placeholder: str | None, depth: int = 0) -> Dict[str, Any] | None:
        if not placeholder or depth > 5:
            return None
        clean = str(placeholder).strip()
        m_zone = re.match(r"^([1-6])[°ºª]?\s*(?:ZONA\s+|GRUPO\s+)?([A-Z])$", clean, re.IGNORECASE)
        if m_zone:
            pos = int(m_zone.group(1))
            letter = m_zone.group(2).upper()
            zona = find_zone_by_letter(letter)
            if not zona or not is_zone_finished(zona["id"]):
                return None
            standings = calc_zone_standings(zona["id"])
            return standings[pos - 1] if 0 <= pos - 1 < len(standings) else None

        m_match = re.match(r"^(G(?:ANADOR)?|W|P(?:ERDEDOR)?|L)\s*(?:PARTIDO\s+|P\.?\s*|#|-)?\s*(\d+)$", clean, re.IGNORECASE)
        if m_match:
            is_win = m_match.group(1).upper().startswith(("G", "W"))
            target_num = int(m_match.group(2))
            target_match = next((p for p in partidos if _extract_match_num(p) == target_num), None)
            if not target_match or not _is_finished(target_match):
                return None
            gl, gv = _get_scores(target_match)
            if gl is None or gv is None or gl == gv:
                return None
            loc_team = resolve_side(target_match, "local", depth + 1)
            vis_team = resolve_side(target_match, "visitante", depth + 1)
            loc_won = gl > gv
            return (loc_team if loc_won else vis_team) if is_win else (vis_team if loc_won else loc_team)

        return None

    def resolve_side(p: Dict[str, Any], side: str, depth: int = 0) -> Dict[str, Any] | None:
        is_loc = side == "local"
        direct_id = p.get("equipoLocalId") if is_loc else p.get("equipoVisitanteId")
        placeholder = p.get("placeholderLocal") if is_loc else p.get("placeholderVisitante")
        if placeholder:
            res = resolve_placeholder(placeholder, depth)
            if res:
                return res
        if direct_id and direct_id in clubes_map:
            return clubes_map[direct_id]
        return None

    def format_placeholder_label(raw: str | None) -> str:
        if not raw:
            return "Por definir"
        s = str(raw).strip()
        mz = re.match(r"^([1-6])[°ºª]?\s*(?:ZONA\s+|GRUPO\s+)?([A-Z])$", s, re.IGNORECASE)
        if mz:
            return f"{mz.group(1)}° Grupo {mz.group(2).upper()}"
        mp = re.match(r"^(G|P)\s*(\d+)$", s, re.IGNORECASE)
        if mp:
            return f"{'Ganador' if mp.group(1).upper() == 'G' else 'Perdedor'} Partido {mp.group(2)}"
        return s

    # 1. Actualizar partidos de Fase de Grupos en all_matches
    base_group_matches = [m for m in all_matches if not m.get("is_playoff_auto")]
    group_sitas_fs = [
        p for p in partidos
        if not p.get("es_playoff") and (
            is_club_sitas(clubes_map.get(p.get("equipoLocalId")), str(p.get("equipoLocalId") or ""))
            or is_club_sitas(clubes_map.get(p.get("equipoVisitanteId")), str(p.get("equipoVisitanteId") or ""))
        )
    ]

    for fp in group_sitas_fs:
        loc = clubes_map.get(fp.get("equipoLocalId"))
        vis = clubes_map.get(fp.get("equipoVisitanteId"))
        loc_name = loc.get("nombre", "") if loc else ""
        vis_name = vis.get("nombre", "") if vis else ""
        rival_fs = vis_name if is_club_sitas(loc, loc_name) else loc_name
        rival_norm = _strip_accents(rival_fs).lower()

        for bm in base_group_matches:
            if not bm.get("is_sitas"):
                continue
            bm_rival = bm["away_team"] if re.search(r"sitas", str(bm.get("home_team") or ""), re.IGNORECASE) else bm["home_team"]
            bm_rival_norm = _strip_accents(str(bm_rival)).lower()
            if rival_norm and bm_rival_norm and (rival_norm in bm_rival_norm or bm_rival_norm in rival_norm):
                bm_home_sitas = bool(re.search(r"sitas", str(bm.get("home_team") or ""), re.IGNORECASE))
                fp_loc_sitas = is_club_sitas(loc, loc_name)
                same_order = bm_home_sitas == fp_loc_sitas
                if loc and loc.get("escudo_url"):
                    bm["home_logo" if same_order else "away_logo"] = loc["escudo_url"]
                if vis and vis.get("escudo_url"):
                    bm["away_logo" if same_order else "home_logo"] = vis["escudo_url"]
                fin = _is_finished(fp)
                live = _is_live(fp)
                gl, gv = _get_scores(fp)
                if (fin or live) and gl is not None and gv is not None:
                    bm["played"] = fin
                    bm["is_live"] = live
                    bm["home_score"] = gl if same_order else gv
                    bm["away_score"] = gv if same_order else gl
                pd = fp.get("planilla_digital") if isinstance(fp.get("planilla_digital"), dict) else {}
                if pd.get("arbitro1Nombre"):
                    bm["ref1"] = pd["arbitro1Nombre"]
                if pd.get("arbitro2Nombre"):
                    bm["ref2"] = pd["arbitro2Nombre"]
                if fp.get("streaming_url"):
                    bm["streaming_url"] = fp["streaming_url"]

    # 2. Agregar Playoffs de SITAS
    playoff_cards: List[Dict[str, Any]] = []
    added_nums: set[int] = set()

    fs_playoffs = sorted(
        [p for p in partidos if p.get("es_playoff")],
        key=lambda x: _extract_match_num(x) or 999,
    )
    for fp in fs_playoffs:
        loc_team = resolve_side(fp, "local")
        vis_team = resolve_side(fp, "visitante")
        if not is_club_sitas(loc_team) and not is_club_sitas(vis_team):
            continue
        m_num = _extract_match_num(fp)
        if m_num:
            added_nums.add(m_num)
        sched_fb = LIGA_FEDERAL_PLAYOFF_SCHEDULE.get(m_num or 0, {})
        raw_stage = re.sub(r"\s*\((fase\s+[^)]+|campeonato|estímulo|estimulo)\)", "", str(fp.get("fase") or sched_fb.get("round_num") or "Playoff"), flags=re.IGNORECASE)
        raw_stage = re.sub(r"\s*-\s*Partido\s*\d+", "", raw_stage, flags=re.IGNORECASE).strip()

        home_name = loc_team["nombre"] if loc_team else format_placeholder_label(fp.get("placeholderLocal") or sched_fb.get("pLocal"))
        away_name = vis_team["nombre"] if vis_team else format_placeholder_label(fp.get("placeholderVisitante") or sched_fb.get("pVis"))
        fin = _is_finished(fp)
        live = _is_live(fp)
        gl, gv = _get_scores(fp)
        has_sc = (fin or live) and gl is not None and gv is not None
        pd = fp.get("planilla_digital") if isinstance(fp.get("planilla_digital"), dict) else {}

        playoff_cards.append({
            "division": "MAYORES",
            "round_num": raw_stage,
            "match_date": _format_date(fp.get("fecha"), sched_fb.get("match_date", "21/11/2026")),
            "time": _format_time(fp.get("hora"), sched_fb.get("time", "-")),
            "category": "LIGA FEDERAL",
            "home_team": home_name,
            "away_team": away_name,
            "home_logo": loc_team.get("escudo_url") if loc_team else None,
            "away_logo": vis_team.get("escudo_url") if vis_team else None,
            "venue": _resolve_venue(fp, sched_fb.get("venue", "Por definir")),
            "ref1": pd.get("arbitro1Nombre", ""),
            "ref2": pd.get("arbitro2Nombre", ""),
            "observations": f"Partido {m_num}" if m_num else "",
            "is_sitas": 1,
            "is_playoff_auto": True,
            "played": fin,
            "is_live": live,
            "home_score": gl if has_sc else None,
            "away_score": gv if has_sc else None,
            "streaming_url": fp.get("streaming_url"),
        })

    for m_num, cfg in LIGA_FEDERAL_PLAYOFF_SCHEDULE.items():
        if m_num in added_nums:
            continue
        loc_team = resolve_placeholder(cfg["pLocal"])
        vis_team = resolve_placeholder(cfg["pVis"])
        if not is_club_sitas(loc_team) and not is_club_sitas(vis_team):
            continue
        added_nums.add(m_num)
        playoff_cards.append({
            "division": "MAYORES",
            "round_num": cfg["round_num"],
            "match_date": cfg["match_date"],
            "time": cfg["time"],
            "category": "LIGA FEDERAL",
            "home_team": loc_team["nombre"] if loc_team else format_placeholder_label(cfg["pLocal"]),
            "away_team": vis_team["nombre"] if vis_team else format_placeholder_label(cfg["pVis"]),
            "home_logo": loc_team.get("escudo_url") if loc_team else None,
            "away_logo": vis_team.get("escudo_url") if vis_team else None,
            "venue": cfg["venue"],
            "ref1": "",
            "ref2": "",
            "observations": f"Partido {m_num}",
            "is_sitas": 1,
            "is_playoff_auto": True,
            "played": False,
            "is_live": False,
            "home_score": None,
            "away_score": None,
        })

    final_matches = base_group_matches + playoff_cards
    payload = {
        "count": len(final_matches),
        "matches": final_matches,
    }
    upcoming_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


if __name__ == "__main__":
    updated = sync_national_schedule_file()
    print(f"Sync national schedule completed: updated={updated}")
