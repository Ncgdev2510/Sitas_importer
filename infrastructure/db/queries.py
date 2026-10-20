"""
Consultas de alto nivel sobre la base de datos (SQLite).
Provee endpoints de datos y generador de JSON para el frontend.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any

from infrastructure.db.database import get_db_connection, DEFAULT_DB_PATH


def get_seasons(conn: sqlite3.Connection | None = None) -> list[str]:
    """Retorna las temporadas disponibles ordenadas descendentemente."""
    c = conn or get_db_connection()
    rows = c.execute("SELECT DISTINCT season FROM tournaments ORDER BY season DESC").fetchall()
    return [r["season"] for r in rows]


def get_categories(season: str | None = None, conn: sqlite3.Connection | None = None) -> list[str]:
    """Retorna las categorías disponibles, opcionalmente filtradas por temporada."""
    c = conn or get_db_connection()
    if season:
        rows = c.execute(
            "SELECT DISTINCT category FROM tournaments WHERE season = ? ORDER BY category",
            (season,),
        ).fetchall()
    else:
        rows = c.execute("SELECT DISTINCT category FROM tournaments ORDER BY category").fetchall()
    return [r["category"] for r in rows if r["category"]]


def get_tournaments_list(
    season: str | None = None,
    category: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    c = conn or get_db_connection()
    query = """
    SELECT t.id, t.clupik_id, t.name, t.season, t.category, t.edition, t.status,
           COUNT(DISTINCT p.id) as total_phases,
           COUNT(DISTINCT m.id) as total_matches
    FROM tournaments t
    LEFT JOIN phases p ON p.tournament_id = t.id
    LEFT JOIN matches m ON m.tournament_id = t.id
    WHERE (t.season = ? OR ? IS NULL)
      AND (t.category = ? OR ? IS NULL)
    GROUP BY t.id
    ORDER BY t.season DESC, t.category ASC, t.edition ASC
    """
    rows = c.execute(query, (season, season, category, category)).fetchall()
    return [dict(r) for r in rows]


def get_tournament_full_detail(tournament_id: int, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    c = conn or get_db_connection()
    t_row = c.execute("SELECT * FROM tournaments WHERE id = ? OR clupik_id = ?", (tournament_id, tournament_id)).fetchone()
    if not t_row:
        return None

    db_t_id = t_row["id"]
    t_dict = dict(t_row)

    # Obtener fases
    phases_rows = c.execute(
        "SELECT * FROM phases WHERE tournament_id = ? ORDER BY id ASC", (db_t_id,)
    ).fetchall()

    phases_data = []
    for p in phases_rows:
        p_dict = dict(p)
        phase_id = p["id"]

        # Tabla de posiciones
        standings_rows = c.execute(
            """
            SELECT s.*, c.name as club_name, c.clupik_id as club_clupik_id
            FROM standings s
            JOIN clubs c ON c.id = s.club_id
            WHERE s.phase_id = ?
            ORDER BY s.position ASC
            """,
            (phase_id,),
        ).fetchall()
        p_dict["standings"] = [dict(s) for s in standings_rows]

        # Partidos
        matches_rows = c.execute(
            """
            SELECT m.*,
                   hc.name as home_club_name,
                   ac.name as away_club_name
            FROM matches m
            JOIN clubs hc ON hc.id = m.home_club_id
            JOIN clubs ac ON ac.id = m.away_club_id
            WHERE m.phase_id = ?
            ORDER BY m.scheduled_at ASC, m.id ASC
            """,
            (phase_id,),
        ).fetchall()
        p_dict["matches"] = [dict(m) for m in matches_rows]

        # Determinar si es fase de playoff / eliminatorias
        is_playoff = bool(p_dict.get("is_playoff")) or any(
            w in (p["name"] or "").upper() for w in ["COPA", "PLAYOFF", "ORO", "PLATA", "BRONCE"]
        )
        p_dict["is_playoff"] = is_playoff

        if is_playoff:
            round_order = {
                "octav": 1,
                "cuart": 2,
                "semi": 3,
                "final": 4,
                "tercer": 5,
            }

            def _get_round_sort(r_name: str) -> int:
                r_lower = (r_name or "").lower()
                for k, order in round_order.items():
                    if k in r_lower:
                        return order
                return 99

            rounds_dict: dict[str, list] = {}
            for m in p_dict["matches"]:
                r_name = m.get("round_name") or "Eliminatoria"
                if r_name not in rounds_dict:
                    rounds_dict[r_name] = []
                rounds_dict[r_name].append({
                    "bracket_label": r_name,
                    "match_id": m.get("clupik_id"),
                    "home_club": {"name": m.get("home_club_name")},
                    "away_club": {"name": m.get("away_club_name")},
                    "home_score": m.get("home_score"),
                    "away_score": m.get("away_score"),
                    "played": bool(m.get("played")),
                    "scheduled_at": m.get("scheduled_at"),
                    "venue": m.get("venue"),
                })

            sorted_round_names = sorted(rounds_dict.keys(), key=_get_round_sort)
            p_dict["bracket"] = {
                "rounds": [
                    {
                        "round_name": r_name,
                        "matches": rounds_dict[r_name],
                    }
                    for r_name in sorted_round_names
                ]
            }
        else:
            p_dict["bracket"] = None

        phases_data.append(p_dict)

    t_dict["phases"] = phases_data
    return t_dict


def get_club_summary(club_name: str = "SITAS", conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    c = conn or get_db_connection()
    # Estadísticas globales de posiciones
    standing_stats = c.execute(
        """
        SELECT
            COUNT(DISTINCT s.tournament_id) as tournaments_played,
            SUM(s.played) as total_pj,
            SUM(s.won) as total_pg,
            SUM(s.lost) as total_pp,
            SUM(s.points) as total_pts,
            SUM(s.goals_for) as total_gf,
            SUM(s.goals_against) as total_gc,
            SUM(s.goal_diff) as total_diff
        FROM standings s
        JOIN clubs c ON c.id = s.club_id
        WHERE c.name LIKE ?
        """,
        (f"%{club_name}%",),
    ).fetchone()

    # Partidos recientes
    recent_matches = c.execute(
        """
        SELECT m.*,
               t.season, t.category, t.edition,
               p.name as phase_name,
               hc.name as home_name,
               ac.name as away_name
        FROM matches m
        JOIN tournaments t ON t.id = m.tournament_id
        LEFT JOIN phases p ON p.id = m.phase_id
        JOIN clubs hc ON hc.id = m.home_club_id
        JOIN clubs ac ON ac.id = m.away_club_id
        WHERE hc.name LIKE ? OR ac.name LIKE ?
        ORDER BY m.scheduled_at DESC, m.id DESC
        LIMIT 20
        """,
        (f"%{club_name}%", f"%{club_name}%"),
    ).fetchall()

    return {
        "club": club_name,
        "stats": dict(standing_stats) if standing_stats else {},
        "recent_matches": [dict(m) for m in recent_matches],
    }


def export_data_for_frontend(
    output_path: Path | str = "web_data.json",
    club_name: str = "SITAS",
    conn: sqlite3.Connection | None = None,
) -> Path:
    """
    Genera un archivo JSON optimizado para que el Frontend lo consuma directamente
    con 0 tokens y carga instantánea.
    """
    c = conn or get_db_connection()
    seasons = get_seasons(c)
    tournaments = get_tournaments_list(conn=c)

    tournaments_detailed = []
    for t in tournaments:
        detail = get_tournament_full_detail(t["id"], conn=c)
        if detail:
            tournaments_detailed.append(detail)

    club_summary = get_club_summary(club_name, conn=c)

    payload = {
        "target_club": club_name,
        "seasons": seasons,
        "categories": get_categories(conn=c),
        "tournaments": tournaments_detailed,
        "club_summary": club_summary,
    }

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return out_file


def export_upcoming_for_frontend(
    output_path: Path | str = "web/upcoming.json",
    conn: sqlite3.Connection | None = None,
) -> Path:
    """
    Genera un archivo JSON estático con los próximos partidos para GitHub Pages.
    """
    c = conn or get_db_connection()
    matches = get_upcoming_matches(sitas_only=False, conn=c)
    payload = {
        "count": len(matches),
        "matches": matches,
    }
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return out_file


def export_posts_for_frontend(
    output_path: Path | str = "web/posts.json",
    limit: int = 50,
    conn: sqlite3.Connection | None = None,
) -> Path:
    """
    Genera un archivo JSON estático con las publicaciones del blog para GitHub Pages.
    """
    c = conn or get_db_connection()
    posts = get_posts(limit=limit, published_only=True, conn=c)
    payload = {
        "success": True,
        "count": len(posts),
        "posts": posts,
    }
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return out_file


def export_all_static_data(
    web_dir: Path | str = "web",
    club_name: str = "SITAS",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Path]:
    """
    Exporta todo el dataset estático (data.json, upcoming.json, posts.json)
    para despliegue directo en GitHub Pages sin necesidad de backend en vivo.
    """
    base_web = Path(web_dir)
    c = conn or get_db_connection()
    return {
        "data": export_data_for_frontend(base_web / "data.json", club_name=club_name, conn=c),
        "upcoming": export_upcoming_for_frontend(base_web / "upcoming.json", conn=c),
        "posts": export_posts_for_frontend(base_web / "posts.json", conn=c),
    }



# ==========================================
# Autenticación y Usuarios
# ==========================================
def seed_default_admin(conn: sqlite3.Connection | None = None) -> None:
    """Crea el usuario admin por defecto si no existe."""
    from werkzeug.security import generate_password_hash
    c = conn or get_db_connection()
    row = c.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    if not row:
        pw_hash = generate_password_hash("sitas2026")
        c.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", pw_hash, "admin"),
        )
        if conn is None:
            c.commit()


def verify_user(username: str, password: str, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    """Verifica credenciales de usuario."""
    from werkzeug.security import check_password_hash
    c = conn or get_db_connection()
    row = c.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row and check_password_hash(row["password_hash"], password):
        return {"id": row["id"], "username": row["username"], "role": row["role"]}
    return None


def get_user_by_id(user_id: int, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    c = conn or get_db_connection()
    row = c.execute("SELECT id, username, role, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


# ==========================================
# Módulo de Noticias / Blog
# ==========================================
def get_posts(limit: int = 50, published_only: bool = True, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    c = conn or get_db_connection()
    query = """
    SELECT p.*, u.username as author_name
    FROM posts p
    LEFT JOIN users u ON u.id = p.author_id
    """
    if published_only:
        query += " WHERE p.published = 1"
    query += " ORDER BY p.published_at DESC, p.id DESC LIMIT ?"
    rows = c.execute(query, (limit,)).fetchall()
    return [dict(r) for r in rows]


def get_post_by_id(post_id: int, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    c = conn or get_db_connection()
    row = c.execute(
        """
        SELECT p.*, u.username as author_name
        FROM posts p
        LEFT JOIN users u ON u.id = p.author_id
        WHERE p.id = ?
        """,
        (post_id,),
    ).fetchone()
    return dict(row) if row else None


def create_post(
    title: str,
    content: str,
    category: str = "General",
    summary: str | None = None,
    image_url: str | None = None,
    author_id: int | None = None,
    published: bool = True,
    conn: sqlite3.Connection | None = None,
) -> int:
    c = conn or get_db_connection()
    cur = c.execute(
        """
        INSERT INTO posts (title, category, summary, content, image_url, author_id, published)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (title, category, summary, content, image_url, author_id, 1 if published else 0),
    )
    if conn is None:
        c.commit()
    return cur.lastrowid


def delete_post(post_id: int, conn: sqlite3.Connection | None = None) -> bool:

    c = conn or get_db_connection()
    c.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    if conn is None:
        c.commit()
    return True


def update_post(
    post_id: int,
    title: str,
    content: str,
    category: str = "General",
    summary: str | None = None,
    image_url: str | None = None,
    published: bool = True,
    conn: sqlite3.Connection | None = None,
) -> bool:
    c = conn or get_db_connection()
    # Si image_url es None y se pasa explícitamente como None pero no queremos sobreescribir la imagen existente si no cambió,
    # verificamos:
    if image_url is not None:
        c.execute(
            """
            UPDATE posts
            SET title = ?, category = ?, summary = ?, content = ?, image_url = ?, published = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (title, category, summary, content, image_url, 1 if published else 0, post_id),
        )
    else:
        c.execute(
            """
            UPDATE posts
            SET title = ?, category = ?, summary = ?, content = ?, published = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (title, category, summary, content, 1 if published else 0, post_id),
        )
    if conn is None:
        c.commit()
    return True



# ==========================================
# Módulo de Próximos Partidos (Cronograma PDF)
# ==========================================
def save_upcoming_matches(
    matches: list[dict[str, Any]],
    batch_id: str | None = None,
    clear_previous: bool = True,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Guarda los partidos importados de un cronograma PDF."""
    c = conn or get_db_connection()
    if clear_previous:
        c.execute("DELETE FROM upcoming_matches")

    count = 0
    for m in matches:
        c.execute(
            """
            INSERT INTO upcoming_matches (
                division, round_num, match_date, time, category,
                home_team, away_team, venue, ref1, ref2, observations,
                is_sitas, batch_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                m.get("division"),
                m.get("round_num"),
                m.get("match_date"),
                m.get("time"),
                m.get("category"),
                m.get("home_team"),
                m.get("away_team"),
                m.get("venue"),
                m.get("ref1"),
                m.get("ref2"),
                m.get("observations"),
                1 if m.get("is_sitas") else 0,
                batch_id,
            ),
        )
        count += 1

    if conn is None:
        c.commit()
    return count


def get_upcoming_matches(
    sitas_only: bool = False,
    division: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    c = conn or get_db_connection()
    query = "SELECT * FROM upcoming_matches WHERE 1=1"
    params: list[Any] = []
    if sitas_only:
        query += " AND is_sitas = 1"
    if division:
        query += " AND division = ?"
        params.append(division)
    query += " ORDER BY match_date ASC, time ASC, category ASC, id ASC"
    rows = c.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def clear_upcoming_matches(conn: sqlite3.Connection | None = None) -> None:
    c = conn or get_db_connection()
    c.execute("DELETE FROM upcoming_matches")
    if conn is None:
        c.commit()

