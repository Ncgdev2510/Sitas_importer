"""
Importador idempotente para la Liga Federal Primera Femenina 2026 (Chaco)
a partir de los datos oficiales del sistema de la Confederación Argentina de Cestoball
(torneo ID: gmJz8jfk0aJ8wcUiImXN).

Carga el torneo en sitas.db con exactamente la misma estructura relacional y
cuadros eliminatorios (bracket_data) que las Ligas Nacionales importadas desde Clupik,
sin riesgo de colisión con futuras sincronizaciones de Clupik.

Uso:
    python import_liga_federal.py
    python import_liga_federal.py --export
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from infrastructure.db.database import DEFAULT_DB_PATH, db_transaction, init_db
from infrastructure.db.queries import export_data_for_frontend

# IDs sintéticos altos para no colisionar jamás con IDs de Clupik (~1.3M / ~3.7M / ~145M)
TOURNAMENT_CLUPIK_ID = 9202601
PHASE_BASE_ID = 920260100
MATCH_BASE_ID = 9202601000

TOURNAMENT_META = {
    "clupik_id": TOURNAMENT_CLUPIK_ID,
    "season": "2026",
    "category": "LIGA FEDERAL MAYORES FEMENINA",
    "edition": "Chaco 2026",
    "status": "Finalizada",
    "source_id": "gmJz8jfk0aJ8wcUiImXN",
}

# Mapeo de clubes a nombres consistentes con Clupik (con sigla provincial) y logo local
CLUBS: dict[str, dict[str, str]] = {
    "VELEZ": {"name": "VELEZ (CF)", "logo": "assets/clubs/velez.png"},
    "BELGRANO": {"name": "BELGRANO (TU)", "logo": "assets/clubs/belgrano.png"},
    "BOLIVAR": {"name": "BOLIVAR (BA)", "logo": "assets/clubs/bolivar.png"},
    "NAZARENO": {"name": "NAZARENO (MI)", "logo": "assets/clubs/nazareno.png"},
    "DEFENSORES": {"name": "DEFENSORES DEL SUD (SE)", "logo": "assets/clubs/defensoresdelsud.png"},
    "JAIME_ZAPATA": {"name": "JAIME ZAPATA (CH)", "logo": "assets/clubs/jaimezapata.png"},
    "COLON": {"name": "COLON (CT)", "logo": "assets/clubs/colon.png"},
    "ESTUDIANTES": {"name": "ESTUDIANTES (TU)", "logo": "assets/clubs/estudiantes.png"},
    "SOCIAL_PARQUE": {"name": "SOCIAL PARQUE (CF)", "logo": "assets/clubs/socialparque.png"},
    "DEPORTIVO_CUYO": {"name": "DEPORTIVO CUYO (SL)", "logo": "assets/clubs/deportivocuyo.png"},
    "LIBERTAD": {"name": "LIBERTAD (CH)", "logo": "assets/clubs/libertad.png"},
    "LUZ_Y_FUERZA": {"name": "LUZ Y FUERZA (MI)", "logo": "assets/clubs/luzyfuerza.png"},
    "CENTRAL_CORDOBA": {"name": "CENTRAL CORDOBA (SE)", "logo": "assets/clubs/centralcordoba.png"},
    "SITAS": {"name": "SITAS (CF)", "logo": "assets/clubs/sitas.png"},
    "HERCULES": {"name": "HERCULES (CT)", "logo": "assets/clubs/hercules.png"},
    "LEONAS": {"name": "LEONAS (CH)", "logo": "assets/clubs/leonas.png"},
}

# 24 partidos de Fase de Grupos (Partidos 1 al 24)
# Tuplas: (match_num, group_name, round_name, scheduled_at, venue, home_key, away_key, home_score, away_score)
GROUP_MATCHES: list[tuple[int, str, str, str, str, str, str, int, int]] = [
    # GRUPO A
    (1,  "GRUPO A", "Jornada 1", "2026-11-19 09:00:00", "Predio Social CPCE",         "NAZARENO", "BOLIVAR",   40,  70),
    (2,  "GRUPO A", "Jornada 1", "2026-11-19 09:00:00", "Club CUNE",                  "VELEZ",    "BELGRANO", 120,  82),
    (9,  "GRUPO A", "Jornada 2", "2026-11-19 17:15:00", "Club CUNE",                  "BOLIVAR",  "BELGRANO",  66,  68),
    (10, "GRUPO A", "Jornada 2", "2026-11-19 17:15:00", "Polideportivo Jaime Zapata", "NAZARENO", "VELEZ",     52, 103),
    (17, "GRUPO A", "Jornada 3", "2026-11-20 09:00:00", "Polideportivo Jaime Zapata", "VELEZ",    "BOLIVAR",  104,  44),
    (18, "GRUPO A", "Jornada 3", "2026-11-20 09:00:00", "Club CUNE",                  "BELGRANO", "NAZARENO", 116,  64),

    # GRUPO B
    (3,  "GRUPO B", "Jornada 1", "2026-11-19 09:00:00", "Polideportivo Jaime Zapata", "COLON",       "JAIME_ZAPATA",  86,  88),
    (4,  "GRUPO B", "Jornada 1", "2026-11-19 10:30:00", "Polideportivo Jaime Zapata", "DEFENSORES",  "ESTUDIANTES",  123,  32),
    (11, "GRUPO B", "Jornada 2", "2026-11-19 17:15:00", "Predio Social CPCE",         "JAIME_ZAPATA","ESTUDIANTES",   86,  84),
    (12, "GRUPO B", "Jornada 2", "2026-11-19 18:45:00", "Club CUNE",                  "COLON",       "DEFENSORES",    45, 101),
    (19, "GRUPO B", "Jornada 3", "2026-11-20 09:00:00", "Predio Social CPCE",         "ESTUDIANTES", "COLON",         68,  86),
    (20, "GRUPO B", "Jornada 3", "2026-11-20 10:30:00", "Polideportivo Jaime Zapata", "DEFENSORES",  "JAIME_ZAPATA", 131,  54),

    # GRUPO C
    (5,  "GRUPO C", "Jornada 1", "2026-11-19 10:30:00", "Predio Social CPCE",         "LUZ_Y_FUERZA",  "LIBERTAD",       46,  90),
    (6,  "GRUPO C", "Jornada 1", "2026-11-19 10:30:00", "Club CUNE",                  "SOCIAL_PARQUE", "DEPORTIVO_CUYO", 80,  48),
    (13, "GRUPO C", "Jornada 2", "2026-11-19 18:45:00", "Predio Social CPCE",         "LIBERTAD",      "DEPORTIVO_CUYO", 58, 110),
    (14, "GRUPO C", "Jornada 2", "2026-11-19 18:45:00", "Polideportivo Jaime Zapata", "LUZ_Y_FUERZA",  "SOCIAL_PARQUE",  50,  96),
    (21, "GRUPO C", "Jornada 3", "2026-11-20 10:30:00", "Club CUNE",                  "SOCIAL_PARQUE", "LIBERTAD",       90,  44),
    (22, "GRUPO C", "Jornada 3", "2026-11-20 10:30:00", "Predio Social CPCE",         "DEPORTIVO_CUYO","LUZ_Y_FUERZA",   86,  48),

    # GRUPO D
    (7,  "GRUPO D", "Jornada 1", "2026-11-19 12:00:00", "Club CUNE",                  "HERCULES",        "LEONAS",          98,  66),
    (8,  "GRUPO D", "Jornada 1", "2026-11-19 12:00:00", "Polideportivo Jaime Zapata", "CENTRAL_CORDOBA", "SITAS",           88,  56),
    (15, "GRUPO D", "Jornada 2", "2026-11-19 20:15:00", "Predio Social CPCE",         "LEONAS",          "SITAS",           72, 106),
    (16, "GRUPO D", "Jornada 2", "2026-11-19 20:15:00", "Polideportivo Jaime Zapata", "HERCULES",        "CENTRAL_CORDOBA", 82, 112),
    (23, "GRUPO D", "Jornada 3", "2026-11-20 12:00:00", "Polideportivo Jaime Zapata", "CENTRAL_CORDOBA", "LEONAS",          92,  74),
    (24, "GRUPO D", "Jornada 3", "2026-11-20 12:00:00", "Club CUNE",                  "SITAS",           "HERCULES",        94,  68),
]

# Validación cruzada con las tablas oficiales del sistema de la Confederación
EXPECTED_GROUP_STANDINGS: dict[str, list[tuple[str, int, int, int, int, int, int, int]]] = {
    "GRUPO A": [
        ("VELEZ",    6, 3, 3, 0, 327, 178,  149),
        ("BELGRANO", 5, 3, 2, 1, 266, 250,   16),
        ("BOLIVAR",  4, 3, 1, 2, 180, 212,  -32),
        ("NAZARENO", 3, 3, 0, 3, 156, 289, -133),
    ],
    "GRUPO B": [
        ("DEFENSORES",   6, 3, 3, 0, 355, 131,  224),
        ("JAIME_ZAPATA", 5, 3, 2, 1, 228, 301,  -73),
        ("COLON",        4, 3, 1, 2, 217, 257,  -40),
        ("ESTUDIANTES",  3, 3, 0, 3, 184, 295, -111),
    ],
    "GRUPO C": [
        ("SOCIAL_PARQUE",  6, 3, 3, 0, 266, 142,  124),
        ("DEPORTIVO_CUYO", 5, 3, 2, 1, 244, 186,   58),
        ("LIBERTAD",       4, 3, 1, 2, 192, 246,  -54),
        ("LUZ_Y_FUERZA",   3, 3, 0, 3, 144, 272, -128),
    ],
    "GRUPO D": [
        ("CENTRAL_CORDOBA", 6, 3, 3, 0, 292, 212,  80),
        ("SITAS",           5, 3, 2, 1, 256, 228,  28),
        ("HERCULES",        4, 3, 1, 2, 248, 272, -24),
        ("LEONAS",          3, 3, 0, 3, 212, 296, -84),
    ],
}

# 24 partidos de Fase Final / Playoffs (Partidos 25 al 48)
# Agrupados en las 4 fases estándar de Clupik para torneos de 16 equipos
# Tuplas: (match_num, round_name, bracket_label, scheduled_at, venue, home_key, away_key, home_score, away_score)
PLAYOFF_PHASES: list[tuple[str, list[tuple[int, str, str, str, str, str, str, int, int]]]] = [
    (
        "PLAYOFF 1º - 4º",
        [
            (29, "Cuartos de final",       "Cuartos de final 1",     "2026-11-21 18:00:00", "Polideportivo Jaime Zapata", "VELEZ",           "JAIME_ZAPATA",   121,  60),
            (30, "Cuartos de final",       "Cuartos de final 2",     "2026-11-21 18:00:00", "Club CUNE",                  "SOCIAL_PARQUE",   "SITAS",           60,  52),
            (31, "Cuartos de final",       "Cuartos de final 3",     "2026-11-21 19:30:00", "Polideportivo Jaime Zapata", "DEFENSORES",      "BELGRANO",       114,  70),
            (32, "Cuartos de final",       "Cuartos de final 4",     "2026-11-21 19:30:00", "Club CUNE",                  "CENTRAL_CORDOBA", "DEPORTIVO_CUYO", 115,  98),
            (39, "Semifinal",              "Semifinal 1",            "2026-11-22 11:00:00", "Polideportivo Jaime Zapata", "VELEZ",           "SOCIAL_PARQUE",   81,  61),
            (40, "Semifinal",              "Semifinal 2",            "2026-11-22 12:30:00", "Polideportivo Jaime Zapata", "DEFENSORES",      "CENTRAL_CORDOBA",128, 121),
            (47, "Tercer y cuarto puesto", "Tercer y cuarto puesto", "2026-11-23 09:00:00", "Polideportivo Jaime Zapata", "SOCIAL_PARQUE",   "CENTRAL_CORDOBA", 92,  95),
            (48, "Final",                  "Final",                  "2026-11-23 11:00:00", "Polideportivo Jaime Zapata", "VELEZ",           "DEFENSORES",     113, 130),
        ],
    ),
    (
        "PLAYOFF 5º - 8º",
        [
            (37, "Semifinal",  "Semifinal 1", "2026-11-22 11:00:00", "Club CUNE",                  "JAIME_ZAPATA", "SITAS",          74, 80),
            (38, "Semifinal",  "Semifinal 2", "2026-11-22 12:30:00", "Club CUNE",                  "BELGRANO",     "DEPORTIVO_CUYO", 48, 74),
            (46, "5° PUESTO",  "5° PUESTO",   "2026-11-22 20:15:00", "Polideportivo Jaime Zapata", "SITAS",        "DEPORTIVO_CUYO", 78, 79),
            (45, "7° PUESTO",  "7° PUESTO",   "2026-11-22 18:45:00", "Polideportivo Jaime Zapata", "JAIME_ZAPATA", "BELGRANO",       69, 92),
        ],
    ),
    (
        "PLAYOFF 9º - 12º",
        [
            (25, "Cuartos de final", "Cuartos de final 1", "2026-11-21 09:00:00", "Polideportivo Jaime Zapata", "BOLIVAR",  "ESTUDIANTES",  90, 50),
            (26, "Cuartos de final", "Cuartos de final 2", "2026-11-21 09:00:00", "Club CUNE",                  "LIBERTAD", "LEONAS",       79, 68),
            (27, "Cuartos de final", "Cuartos de final 3", "2026-11-21 10:30:00", "Polideportivo Jaime Zapata", "COLON",    "NAZARENO",     84, 54),
            (28, "Cuartos de final", "Cuartos de final 4", "2026-11-21 10:30:00", "Club CUNE",                  "HERCULES", "LUZ_Y_FUERZA", 87, 28),
            (35, "Semifinal",        "Semifinal 1",        "2026-11-22 09:30:00", "Polideportivo Jaime Zapata", "BOLIVAR",  "LIBERTAD",     68, 48),
            (36, "Semifinal",        "Semifinal 2",        "2026-11-22 09:30:00", "Club CUNE",                  "COLON",    "HERCULES",     62, 78),
            (44, "9° PUESTO",        "9° PUESTO",          "2026-11-22 17:15:00", "Polideportivo Jaime Zapata", "BOLIVAR",  "HERCULES",     66, 86),
            (43, "11° PUESTO",       "11° PUESTO",         "2026-11-22 20:15:00", "Club CUNE",                  "LIBERTAD", "COLON",        66, 75),
        ],
    ),
    (
        "PLAYOFF 13º - 16º",
        [
            (33, "Semifinal",   "Semifinal 1", "2026-11-22 08:00:00", "Polideportivo Jaime Zapata", "ESTUDIANTES", "LEONAS",       92, 98),
            (34, "Semifinal",   "Semifinal 2", "2026-11-22 08:00:00", "Club CUNE",                  "NAZARENO",    "LUZ_Y_FUERZA", 74, 38),
            (42, "13° PUESTO",  "13° PUESTO",  "2026-11-22 18:45:00", "Club CUNE",                  "LEONAS",      "NAZARENO",     82, 88),
            (41, "15° PUESTO",  "15° PUESTO",  "2026-11-22 17:15:00", "Club CUNE",                  "ESTUDIANTES", "LUZ_Y_FUERZA", 59, 44),
        ],
    ),
]

# Orden final oficial del torneo (1° al 16°) determinado por los partidos de definición
FINAL_RANKING_ORDER: list[str] = [
    "DEFENSORES",       # 1° (Campeón)
    "VELEZ",            # 2° (Subcampeón)
    "CENTRAL_CORDOBA",  # 3°
    "SOCIAL_PARQUE",    # 4°
    "DEPORTIVO_CUYO",   # 5°
    "SITAS",            # 6°
    "BELGRANO",         # 7°
    "JAIME_ZAPATA",     # 8°
    "HERCULES",         # 9°
    "BOLIVAR",          # 10°
    "COLON",            # 11°
    "LIBERTAD",         # 12°
    "NAZARENO",         # 13°
    "LEONAS",           # 14°
    "ESTUDIANTES",      # 15°
    "LUZ_Y_FUERZA",     # 16°
]


def compute_group_standings(group_name: str) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for _, grp, _, _, _, hk, ak, hs, as_ in GROUP_MATCHES:
        if grp != group_name:
            continue
        for k in (hk, ak):
            if k not in stats:
                stats[k] = {"key": k, "played": 0, "won": 0, "drawn": 0, "lost": 0, "points": 0, "goals_for": 0, "goals_against": 0, "goal_diff": 0}
        h = stats[hk]
        a = stats[ak]
        h["played"] += 1
        a["played"] += 1
        h["goals_for"] += hs
        h["goals_against"] += as_
        a["goals_for"] += as_
        a["goals_against"] += hs
        if hs > as_:
            h["won"] += 1
            h["points"] += 2
            a["lost"] += 1
            a["points"] += 1
        else:
            a["won"] += 1
            a["points"] += 2
            h["lost"] += 1
            h["points"] += 1

    rows = list(stats.values())
    for r in rows:
        r["goal_diff"] = r["goals_for"] - r["goals_against"]
    rows.sort(key=lambda r: (r["points"], r["goal_diff"], r["goals_for"]), reverse=True)

    # Verificar exactitud contra la tabla oficial de la Confederación
    expected = EXPECTED_GROUP_STANDINGS[group_name]
    assert len(rows) == len(expected), f"{group_name}: cantidad de equipos distinta"
    for idx, (row, exp) in enumerate(zip(rows, expected), start=1):
        exp_key, exp_pts, exp_pj, exp_pg, exp_pp, exp_gf, exp_gc, exp_dg = exp
        actual = (row["key"], row["points"], row["played"], row["won"], row["lost"], row["goals_for"], row["goals_against"], row["goal_diff"])
        assert actual == exp, f"{group_name} pos {idx}: calculado {actual} != oficial {exp}"
        row["position"] = idx
    return rows


def build_playoff_bracket(matches: list[tuple[int, str, str, str, str, str, str, int, int]]) -> dict[str, Any]:
    rounds_order: list[str] = []
    rounds_map: dict[str, list[dict[str, Any]]] = {}

    for m_num, r_name, label, sched, venue, hk, ak, hs, as_ in matches:
        if r_name not in rounds_map:
            rounds_map[r_name] = []
            rounds_order.append(r_name)

        h_win = hs > as_
        a_win = as_ > hs
        m_id = MATCH_BASE_ID + m_num
        rounds_map[r_name].append({
            "bracket_label": label,
            "match_id": m_id,
            "round_name": r_name,
            "home_club": {
                "name": CLUBS[hk]["name"],
                "logo_url": CLUBS[hk]["logo"],
                "is_winner": h_win,
            },
            "away_club": {
                "name": CLUBS[ak]["name"],
                "logo_url": CLUBS[ak]["logo"],
                "is_winner": a_win,
            },
            "is_series": False,
            "series_winner": "home" if h_win else "away",
            "games": [{
                "match_id": m_id,
                "game_number": 1,
                "home_score": hs,
                "away_score": as_,
                "home_winner": h_win,
                "away_winner": a_win,
                "played": True,
            }],
            "home_score": hs,
            "away_score": as_,
            "played": True,
            "is_finished": True,
            "scheduled_at": sched,
            "venue": venue,
        })

    return {
        "rounds": [
            {"round_index": idx, "round_name": r_name, "matches": rounds_map[r_name]}
            for idx, r_name in enumerate(rounds_order)
        ]
    }


def compute_playoff_phase_standings(
    phase_name: str,
    matches: list[tuple[int, str, str, str, str, str, str, int, int]],
) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for _, _, _, _, _, hk, ak, hs, as_ in matches:
        for k in (hk, ak):
            if k not in stats:
                stats[k] = {"key": k, "played": 0, "won": 0, "drawn": 0, "lost": 0, "points": 0, "goals_for": 0, "goals_against": 0, "goal_diff": 0}
        h, a = stats[hk], stats[ak]
        h["played"] += 1
        a["played"] += 1
        h["goals_for"] += hs
        h["goals_against"] += as_
        a["goals_for"] += as_
        a["goals_against"] += hs
        if hs > as_:
            h["won"] += 1
            h["points"] += 2
            a["lost"] += 1
            a["points"] += 1
        else:
            a["won"] += 1
            a["points"] += 2
            h["lost"] += 1
            h["points"] += 1

    rows = list(stats.values())
    for r in rows:
        r["goal_diff"] = r["goals_for"] - r["goals_against"]

    rank_idx = {k: i for i, k in enumerate(FINAL_RANKING_ORDER)}
    rows.sort(key=lambda r: rank_idx.get(r["key"], 99))
    for idx, r in enumerate(rows, start=1):
        r["position"] = idx
    return rows


def compute_final_overall_standings() -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {
        k: {"key": k, "played": 0, "won": 0, "drawn": 0, "lost": 0, "points": 0, "goals_for": 0, "goals_against": 0, "goal_diff": 0}
        for k in FINAL_RANKING_ORDER
    }

    all_matches: list[tuple[str, str, int, int]] = [
        (hk, ak, hs, as_) for _, _, _, _, _, hk, ak, hs, as_ in GROUP_MATCHES
    ]
    for _, p_matches in PLAYOFF_PHASES:
        for _, _, _, _, _, hk, ak, hs, as_ in p_matches:
            all_matches.append((hk, ak, hs, as_))

    assert len(all_matches) == 48, f"Se esperaban 48 partidos, se encontraron {len(all_matches)}"

    for hk, ak, hs, as_ in all_matches:
        h, a = stats[hk], stats[ak]
        h["played"] += 1
        a["played"] += 1
        h["goals_for"] += hs
        h["goals_against"] += as_
        a["goals_for"] += as_
        a["goals_against"] += hs
        if hs > as_:
            h["won"] += 1
            h["points"] += 2
            a["lost"] += 1
            a["points"] += 1
        else:
            a["won"] += 1
            a["points"] += 2
            h["lost"] += 1
            h["points"] += 1

    rows = []
    for pos, k in enumerate(FINAL_RANKING_ORDER, start=1):
        r = stats[k]
        assert r["played"] == 6, f"{k} tiene {r['played']} partidos (esperados 6)"
        r["goal_diff"] = r["goals_for"] - r["goals_against"]
        r["position"] = pos
        rows.append(r)
    return rows


def get_or_create_club(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute("SELECT id FROM clubs WHERE name = ?", (name,)).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute("INSERT INTO clubs (clupik_id, name) VALUES (NULL, ?)", (name,))
    return int(cur.lastrowid)


def upsert_phase(
    conn: sqlite3.Connection,
    tournament_id: int,
    clupik_phase_id: int,
    name: str,
    is_active: bool,
    is_playoff: bool,
    bracket_data: dict[str, Any] | None,
) -> int:
    bracket_json = json.dumps(bracket_data, ensure_ascii=False) if bracket_data else None
    row = conn.execute(
        "SELECT id FROM phases WHERE tournament_id = ? AND clupik_phase_id = ?",
        (tournament_id, clupik_phase_id),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE phases SET name = ?, is_active = ?, is_playoff = ?, bracket_data = ? WHERE id = ?",
            (name, 1 if is_active else 0, 1 if is_playoff else 0, bracket_json, row["id"]),
        )
        return int(row["id"])
    cur = conn.execute(
        """
        INSERT INTO phases (tournament_id, clupik_phase_id, name, is_active, is_playoff, bracket_data)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (tournament_id, clupik_phase_id, name, 1 if is_active else 0, 1 if is_playoff else 0, bracket_json),
    )
    return int(cur.lastrowid)


def upsert_standing(conn: sqlite3.Connection, tournament_id: int, phase_id: int, club_id: int, s: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO standings (
            tournament_id, phase_id, club_id, position,
            played, won, drawn, lost, points,
            goals_for, goals_against, goal_diff, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(phase_id, club_id) DO UPDATE SET
            position = excluded.position,
            played = excluded.played,
            won = excluded.won,
            drawn = excluded.drawn,
            lost = excluded.lost,
            points = excluded.points,
            goals_for = excluded.goals_for,
            goals_against = excluded.goals_against,
            goal_diff = excluded.goal_diff,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            tournament_id, phase_id, club_id, s["position"],
            s["played"], s["won"], s["drawn"], s["lost"], s["points"],
            s["goals_for"], s["goals_against"], s["goal_diff"],
        ),
    )


def upsert_match(
    conn: sqlite3.Connection,
    clupik_id: int,
    tournament_id: int,
    phase_id: int,
    round_name: str,
    scheduled_at: str,
    home_club_id: int,
    away_club_id: int,
    home_score: int,
    away_score: int,
    venue: str,
) -> None:
    conn.execute(
        """
        INSERT INTO matches (
            clupik_id, tournament_id, phase_id, round_name,
            scheduled_at, home_club_id, away_club_id,
            home_score, away_score, venue, played, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
        ON CONFLICT(clupik_id) DO UPDATE SET
            tournament_id = excluded.tournament_id,
            phase_id = excluded.phase_id,
            round_name = excluded.round_name,
            scheduled_at = excluded.scheduled_at,
            home_club_id = excluded.home_club_id,
            away_club_id = excluded.away_club_id,
            home_score = excluded.home_score,
            away_score = excluded.away_score,
            venue = excluded.venue,
            played = excluded.played,
            updated_at = CURRENT_TIMESTAMP
        """,
        (clupik_id, tournament_id, phase_id, round_name, scheduled_at, home_club_id, away_club_id, home_score, away_score, venue),
    )


def import_liga_federal(db_path: Path = DEFAULT_DB_PATH) -> dict[str, int]:
    # Pre-validar todas las tablas antes de escribir en la DB
    group_names = ["GRUPO A", "GRUPO B", "GRUPO C", "GRUPO D"]
    group_standings = {g: compute_group_standings(g) for g in group_names}
    overall_standings = compute_final_overall_standings()

    init_db(db_path)

    counts = {"phases": 0, "standings": 0, "matches": 0}

    with db_transaction(db_path) as conn:
        t_name = f"{TOURNAMENT_META['season']} | {TOURNAMENT_META['category']} | {TOURNAMENT_META['edition']}"
        t_row = conn.execute(
            "SELECT id FROM tournaments WHERE clupik_id = ?", (TOURNAMENT_META["clupik_id"],)
        ).fetchone()
        if t_row:
            conn.execute(
                """
                UPDATE tournaments
                SET name = ?, season = ?, category = ?, edition = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (t_name, TOURNAMENT_META["season"], TOURNAMENT_META["category"], TOURNAMENT_META["edition"], TOURNAMENT_META["status"], t_row["id"]),
            )
            db_t_id = int(t_row["id"])
        else:
            cur = conn.execute(
                """
                INSERT INTO tournaments (clupik_id, name, season, category, edition, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (TOURNAMENT_META["clupik_id"], t_name, TOURNAMENT_META["season"], TOURNAMENT_META["category"], TOURNAMENT_META["edition"], TOURNAMENT_META["status"]),
            )
            db_t_id = int(cur.lastrowid)

        club_db_ids = {k: get_or_create_club(conn, cfg["name"]) for k, cfg in CLUBS.items()}

        phase_seq = 1

        # 1. Fases de Grupos (GRUPO A..D)
        for g_idx, g_name in enumerate(group_names):
            p_id = upsert_phase(
                conn,
                db_t_id,
                PHASE_BASE_ID + phase_seq,
                g_name,
                is_active=(g_idx == 0),
                is_playoff=False,
                bracket_data=None,
            )
            phase_seq += 1
            counts["phases"] += 1

            for s in group_standings[g_name]:
                upsert_standing(conn, db_t_id, p_id, club_db_ids[s["key"]], s)
                counts["standings"] += 1

            for m_num, grp, r_name, sched, venue, hk, ak, hs, as_ in GROUP_MATCHES:
                if grp != g_name:
                    continue
                upsert_match(
                    conn,
                    MATCH_BASE_ID + m_num,
                    db_t_id,
                    p_id,
                    r_name,
                    sched,
                    club_db_ids[hk],
                    club_db_ids[ak],
                    hs,
                    as_,
                    venue,
                )
                counts["matches"] += 1

        # 2. Fases de Playoffs (1°-4°, 5°-8°, 9°-12°, 13°-16°)
        for p_name, p_matches in PLAYOFF_PHASES:
            bracket = build_playoff_bracket(p_matches)
            p_id = upsert_phase(
                conn,
                db_t_id,
                PHASE_BASE_ID + phase_seq,
                p_name,
                is_active=False,
                is_playoff=True,
                bracket_data=bracket,
            )
            phase_seq += 1
            counts["phases"] += 1

            for s in compute_playoff_phase_standings(p_name, p_matches):
                upsert_standing(conn, db_t_id, p_id, club_db_ids[s["key"]], s)
                counts["standings"] += 1

            for m_num, r_name, _, sched, venue, hk, ak, hs, as_ in p_matches:
                upsert_match(
                    conn,
                    MATCH_BASE_ID + m_num,
                    db_t_id,
                    p_id,
                    r_name,
                    sched,
                    club_db_ids[hk],
                    club_db_ids[ak],
                    hs,
                    as_,
                    venue,
                )
                counts["matches"] += 1

        # 3. Posiciones Finales (Tabla General 1° al 16° - sin duplicar partidos)
        p_final_id = upsert_phase(
            conn,
            db_t_id,
            PHASE_BASE_ID + phase_seq,
            "POSICIONES FINALES",
            is_active=False,
            is_playoff=False,
            bracket_data=None,
        )
        counts["phases"] += 1
        for s in overall_standings:
            upsert_standing(conn, db_t_id, p_final_id, club_db_ids[s["key"]], s)
            counts["standings"] += 1

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa Liga Federal Femenina 2026 a sitas.db")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Ruta a sitas.db")
    parser.add_argument("--export", action="store_true", help="Regenerar web/data.json al finalizar")
    args = parser.parse_args()

    counts = import_liga_federal(args.db)
    print(f"[OK] Liga Federal Primera Femenina 2026 importada en {args.db.name}:")
    print(f"     - Fases:      {counts['phases']} (Grupos A-D + Playoffs 1°-16° + Posiciones Finales)")
    print(f"     - Posiciones: {counts['standings']} registros")
    print(f"     - Partidos:   {counts['matches']} partidos verificados")

    if args.export:
        out = export_data_for_frontend(BASE_DIR / "web" / "data.json", club_name="SITAS")
        print(f"[OK] Exportado {out} ({round(out.stat().st_size / 1024, 1)} KB)")


if __name__ == "__main__":
    main()
