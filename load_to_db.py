"""
Cargador de datos a Base de Datos (SQLite / PostgreSQL).

Lee archivos JSON generados por main.py (ej. sitas_data.json) y realiza
UPSERT idempotente de clubes, torneos, fases, clasificaciones y partidos.

Uso:
    python load_to_db.py --file sitas_data.json
    python load_to_db.py --file sitas_data.json --db sitas.db
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from pathlib import Path

from infrastructure.db.database import db_transaction, init_db, DEFAULT_DB_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def get_or_create_club(conn: sqlite3.Connection, name: str, clupik_id: int | None) -> int:
    """Busca o crea un club en la base de datos y retorna su ID."""
    name = name.strip()
    if not name:
        return 0

    if clupik_id is not None:
        row = conn.execute(
            "SELECT id FROM clubs WHERE clupik_id = ?", (clupik_id,)
        ).fetchone()
        if row:
            # Actualizamos nombre si cambió
            conn.execute(
                "UPDATE clubs SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (name, row["id"]),
            )
            return row["id"]

    # Buscar por nombre exacto
    row = conn.execute("SELECT id, clupik_id FROM clubs WHERE name = ?", (name,)).fetchone()
    if row:
        if clupik_id is not None and row["clupik_id"] is None:
            conn.execute(
                "UPDATE clubs SET clupik_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (clupik_id, row["id"]),
            )
        return row["id"]

    # Insertar nuevo club
    cursor = conn.execute(
        "INSERT INTO clubs (clupik_id, name) VALUES (?, ?)", (clupik_id, name)
    )
    return cursor.lastrowid


def upsert_tournament(
    conn: sqlite3.Connection,
    clupik_id: int,
    season: str,
    category: str | None,
    edition: str | None,
    manager_name: str | None,
    status: str | None = None,
) -> int:
    name = f"{season} | {category or ''} | {edition or ''}".strip(" |")
    row = conn.execute(
        "SELECT id FROM tournaments WHERE clupik_id = ?", (clupik_id,)
    ).fetchone()

    if row:
        conn.execute(
            """
            UPDATE tournaments
            SET name = ?, season = ?, category = ?, edition = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (name, season, category, edition, status, row["id"]),
        )
        return row["id"]
    else:
        cursor = conn.execute(
            """
            INSERT INTO tournaments (clupik_id, name, season, category, edition, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (clupik_id, name, season, category, edition, status),
        )
        return cursor.lastrowid


def upsert_phase(
    conn: sqlite3.Connection,
    tournament_id: int,
    clupik_phase_id: int,
    name: str,
    is_active: bool,
    is_playoff: bool = False,
    bracket_data: str | None = None,
) -> int:
    row = conn.execute(
        "SELECT id FROM phases WHERE tournament_id = ? AND clupik_phase_id = ?",
        (tournament_id, clupik_phase_id),
    ).fetchone()

    if row:
        conn.execute(
            "UPDATE phases SET name = ?, is_active = ?, is_playoff = ?, bracket_data = ? WHERE id = ?",
            (name, is_active, 1 if is_playoff else 0, bracket_data, row["id"]),
        )
        return row["id"]
    else:
        cursor = conn.execute(
            """
            INSERT INTO phases (tournament_id, clupik_phase_id, name, is_active, is_playoff, bracket_data)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (tournament_id, clupik_phase_id, name, is_active, 1 if is_playoff else 0, bracket_data),
        )
        return cursor.lastrowid


def upsert_standing(
    conn: sqlite3.Connection,
    tournament_id: int,
    phase_id: int,
    club_id: int,
    standing_data: dict,
) -> None:
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
            tournament_id,
            phase_id,
            club_id,
            standing_data.get("position", 0),
            standing_data.get("played", 0),
            standing_data.get("won", 0),
            standing_data.get("drawn", 0),
            standing_data.get("lost", 0),
            standing_data.get("points", 0),
            standing_data.get("goals_for", 0),
            standing_data.get("goals_against", 0),
            standing_data.get("goal_diff", 0),
        ),
    )


def upsert_match(
    conn: sqlite3.Connection,
    tournament_id: int,
    phase_id: int | None,
    home_club_id: int,
    away_club_id: int,
    match_data: dict,
) -> None:
    clupik_id = match_data.get("clupik_id")
    round_name = match_data.get("round_name")
    scheduled_at = match_data.get("scheduled_at")
    home_score = match_data.get("home_score")
    away_score = match_data.get("away_score")
    played = match_data.get("played", False)

    if clupik_id is not None:
        conn.execute(
            """
            INSERT INTO matches (
                clupik_id, tournament_id, phase_id, round_name,
                scheduled_at, home_club_id, away_club_id,
                home_score, away_score, played, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(clupik_id) DO UPDATE SET
                tournament_id = excluded.tournament_id,
                phase_id = excluded.phase_id,
                round_name = excluded.round_name,
                scheduled_at = excluded.scheduled_at,
                home_score = excluded.home_score,
                away_score = excluded.away_score,
                played = excluded.played,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                clupik_id,
                tournament_id,
                phase_id,
                round_name,
                scheduled_at,
                home_club_id,
                away_club_id,
                home_score,
                away_score,
                played,
            ),
        )
    else:
        # Match sin clupik_id explícito
        row = conn.execute(
            """
            SELECT id FROM matches
            WHERE tournament_id = ? AND phase_id = ? AND home_club_id = ? AND away_club_id = ? AND round_name = ?
            """,
            (tournament_id, phase_id, home_club_id, away_club_id, round_name),
        ).fetchone()

        if row:
            conn.execute(
                """
                UPDATE matches
                SET scheduled_at = ?, home_score = ?, away_score = ?, played = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (scheduled_at, home_score, away_score, played, row["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO matches (
                    tournament_id, phase_id, round_name,
                    scheduled_at, home_club_id, away_club_id,
                    home_score, away_score, played
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tournament_id,
                    phase_id,
                    round_name,
                    scheduled_at,
                    home_club_id,
                    away_club_id,
                    home_score,
                    away_score,
                    played,
                ),
            )


def load_data_file(json_file: Path | str, db_path: Path | str | None = None) -> dict[str, int]:
    """Carga un archivo de datos JSON a la base de datos."""
    json_path = Path(json_file)
    if not json_path.exists():
        raise FileNotFoundError(f"Archivo no encontrado: {json_path}")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    tournaments = data.get("tournaments", [])
    logger.info("Cargando %s torneos desde %s...", len(tournaments), json_path.name)

    stats = {
        "tournaments": 0,
        "phases": 0,
        "standings": 0,
        "matches": 0,
        "clubs": 0,
    }

    init_db(db_path)

    with db_transaction(db_path) as conn:
        for t_item in tournaments:
            t_meta = t_item.get("tournament", {})
            clupik_id = t_meta.get("tournament_id")
            if not clupik_id:
                continue

            season = t_meta.get("season") or "Sin temporada"
            category = t_meta.get("category")
            edition = t_meta.get("edition")
            manager_name = t_meta.get("manager_name")
            status = t_meta.get("status")

            db_tournament_id = upsert_tournament(
                conn, clupik_id, season, category, edition, manager_name, status=status
            )
            stats["tournaments"] += 1

            for p_item in t_item.get("phases", []):
                phase_info = p_item.get("phase", {})
                clupik_phase_id = phase_info.get("phase_id")
                phase_name = phase_info.get("name", "Fase")
                is_active = phase_info.get("is_active", False)
                is_playoff = p_item.get("is_playoff", False) or any(
                    w in phase_name.upper() for w in ["COPA", "PLAYOFF", "ORO", "PLATA", "BRONCE"]
                )
                bracket_data = p_item.get("bracket")
                bracket_json = json.dumps(bracket_data, ensure_ascii=False) if bracket_data else None

                if not clupik_phase_id:
                    continue

                db_phase_id = upsert_phase(
                    conn, db_tournament_id, clupik_phase_id, phase_name, is_active, is_playoff, bracket_json
                )
                stats["phases"] += 1

                # Clasificación
                for s in p_item.get("standings", []):
                    club_data = s.get("club", {})
                    club_name = club_data.get("name")
                    if not club_name:
                        continue
                    club_clupik_id = club_data.get("clupik_id")
                    db_club_id = get_or_create_club(conn, club_name, club_clupik_id)
                    upsert_standing(conn, db_tournament_id, db_phase_id, db_club_id, s)
                    stats["standings"] += 1

                # Partidos
                for m in p_item.get("matches", []):
                    home_data = m.get("home_club", {})
                    away_data = m.get("away_club", {})
                    home_name = home_data.get("name")
                    away_name = away_data.get("name")
                    if not home_name or not away_name:
                        continue

                    home_club_id = get_or_create_club(
                        conn, home_name, home_data.get("clupik_id")
                    )
                    away_club_id = get_or_create_club(
                        conn, away_name, away_data.get("clupik_id")
                    )

                    upsert_match(
                        conn,
                        db_tournament_id,
                        db_phase_id,
                        home_club_id,
                        away_club_id,
                        m,
                    )
                    stats["matches"] += 1

        # Contar total de clubes registrados
        club_count = conn.execute("SELECT COUNT(*) FROM clubs").fetchone()[0]
        stats["clubs"] = club_count

    logger.info("Carga completada exitosamente:")
    logger.info("  - Torneos procesados: %s", stats["tournaments"])
    logger.info("  - Fases: %s", stats["phases"])
    logger.info("  - Posiciones cargadas: %s", stats["standings"])
    logger.info("  - Partidos cargados: %s", stats["matches"])
    logger.info("  - Clubes en la base de datos: %s", stats["clubs"])

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga datos JSON de Clupik a base de datos")
    parser.add_argument("--file", type=Path, default=Path("sitas_data.json"), help="Ruta al archivo JSON")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Ruta al archivo SQLite")
    args = parser.parse_args()

    load_data_file(args.file, args.db)
