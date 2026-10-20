"""
Orquestador del importador.

Dos modos de uso:

  1) Ya sabés el tournament_id:
       python main.py --tournament-id 1339117 --club SITAS

  2) No sabés en qué torneos participa el club (caso normal: una
     federación organiza 20-30 torneos por año, uno por categoría, y
     SITAS sólo juega algunos):
       python main.py --manager-id 260550 --club SITAS

     Este modo descubre automáticamente en qué torneos aparece el club,
     revisando la clasificación de la fase por defecto de cada torneo
     del manager, y sólo baja el detalle completo (todas las fases +
     calendario) de los torneos donde el club realmente participa.

Guarda todo en un JSON para inspección manual antes de cargarlo a
PostgreSQL.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path

from infrastructure.clupik.client import ClupikClient
from infrastructure.clupik.parser import (
    parse_tournament_list,
    parse_tournament_metadata,
    parse_ranking_phases,
    parse_standings,
    get_standing_for_club,
    parse_calendar,
    get_matches_for_club,
    is_playoff_phase,
    parse_playoff_bracket,
    generate_playoff_standings,
)
from domain.entities import Tournament

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def extract_tournament(
    client: ClupikClient,
    tournament_id: int,
    club_name: str,
    base_html: str | None = None,
    phase_cache: dict[int, str] | None = None,
    status: str = "",
) -> dict:
    """Baja ranking + calendario de todas las fases de un torneo y filtra por club."""
    if base_html is None:
        base_html = client.get_ranking(tournament_id)
    metadata = parse_tournament_metadata(base_html)
    if status:
        metadata["status"] = status
    phases = parse_ranking_phases(base_html, tournament_id)
    logger.info("  Torneo %s: fases %s", tournament_id, [p["name"] for p in phases])

    result: dict = {"tournament": metadata, "phases": []}
    cache = phase_cache or {}

    for phase in phases:
        phase_id = phase["phase_id"]
        phase_name = phase["name"]

        if phase["is_active"]:
            ranking_html = base_html
        elif phase_id in cache:
            ranking_html = cache[phase_id]
        else:
            ranking_html = client.get_ranking(tournament_id, phase_id)

        is_playoff = is_playoff_phase(ranking_html) if ranking_html else False
        bracket_dict = None

        if is_playoff:
            playoff_matches, bracket_dict = parse_playoff_bracket(
                ranking_html, tournament_id, phase_id, phase_name, season=metadata.get("season", "2026")
            )
            # Enriquecemos con calendario si está disponible para fechas/horas exactas
            calendar_html = client.get_calendar(tournament_id, phase_id)
            if calendar_html:
                cal_matches = parse_calendar(calendar_html, tournament_id, phase_id, phase_name)
                cal_by_id = {m.clupik_id: m for m in cal_matches if m.clupik_id}
                for pm in playoff_matches:
                    if pm.clupik_id and pm.clupik_id in cal_by_id:
                        cm = cal_by_id[pm.clupik_id]
                        if cm.scheduled_at and not pm.scheduled_at:
                            pm.scheduled_at = cm.scheduled_at
                        if cm.played and not pm.played:
                            pm.played = True
                            if pm.home_score is None:
                                pm.home_score = cm.home_score
                                pm.away_score = cm.away_score

            matches = playoff_matches
            standings = generate_playoff_standings(matches, tournament_id, phase_id, phase_name)
            club_standing = get_standing_for_club(standings, club_name)
            club_matches = get_matches_for_club(matches, club_name)
        else:
            standings = parse_standings(ranking_html, tournament_id, phase_id, phase_name) if ranking_html else []
            club_standing = get_standing_for_club(standings, club_name)

            # Si la fase regular no está activa y su tabla está vacía, evitamos request innecesaria de calendario
            if not phase["is_active"] and not standings:
                matches = []
                club_matches = []
            else:
                calendar_html = client.get_calendar(tournament_id, phase_id)
                if calendar_html:
                    matches = parse_calendar(calendar_html, tournament_id, phase_id, phase_name)
                    club_matches = get_matches_for_club(matches, club_name)
                else:
                    matches = []
                    club_matches = []

        result["phases"].append({
            "phase": phase,
            "is_playoff": is_playoff,
            "bracket": bracket_dict,
            "standings": [asdict(s) for s in standings],
            "club_standing": asdict(club_standing) if club_standing else None,
            "matches": [asdict(m) for m in matches],
            "club_matches": [asdict(m) for m in club_matches],
        })

        if club_standing:
            logger.info(
                "    -> %s en %s: posición %s, %s pts (PJ=%s PG=%s PP=%s), %s partidos",
                club_name, phase_name, club_standing.position,
                club_standing.points, club_standing.played,
                club_standing.won, club_standing.lost, len(club_matches),
            )

    return result


def check_club_participation(
    client: ClupikClient, tournament: Tournament, club_name: str
) -> tuple[bool, str, dict[int, str]]:
    """
    Chequeo multi-fase: revisa todas las zonas/fases del torneo (ZONA A, B, C, D,
    FASE REGULAR, COPA DE ORO/PLATA/BRONCE, etc.) para verificar si el club participa.
    Devuelve (participa, base_html, phase_cache).
    """
    base_html = client.get_ranking(tournament.clupik_id)
    phases = parse_ranking_phases(base_html, tournament.clupik_id)
    if not phases:
        return False, base_html, {}

    phase_cache: dict[int, str] = {}
    active_phase = next((p for p in phases if p["is_active"]), phases[0])
    phase_cache[active_phase["phase_id"]] = base_html

    def _participates_in_html(html: str, p_id: int, p_name: str) -> bool:
        if is_playoff_phase(html):
            p_matches, _ = parse_playoff_bracket(html, tournament.clupik_id, p_id, p_name)
            if any(m.involves(club_name) for m in p_matches):
                return True
            p_standings = generate_playoff_standings(p_matches, tournament.clupik_id, p_id, p_name)
            return get_standing_for_club(p_standings, club_name) is not None
        else:
            p_standings = parse_standings(html, tournament.clupik_id, p_id, p_name)
            return get_standing_for_club(p_standings, club_name) is not None

    # 1. Primero chequear la fase activa
    if _participates_in_html(base_html, active_phase["phase_id"], active_phase["name"]):
        return True, base_html, phase_cache

    # 2. Si no está en la fase activa, chequear las demás fases (ej. otras Zonas o Copas)
    for p in phases:
        if p["phase_id"] == active_phase["phase_id"]:
            continue
        p_html = client.get_ranking(tournament.clupik_id, p["phase_id"])
        if p_html:
            phase_cache[p["phase_id"]] = p_html
            if _participates_in_html(p_html, p["phase_id"], p["name"]):
                return True, base_html, phase_cache

    return False, base_html, phase_cache


def club_plays_in(client: ClupikClient, tournament: Tournament, club_name: str) -> bool:
    participates, _, _ = check_club_participation(client, tournament, club_name)
    return participates


def run_by_tournament(client: ClupikClient, tournament_id: int, club_name: str, output_path: Path) -> None:
    logger.info("Descargando torneo %s...", tournament_id)
    result = {"club": club_name, "tournaments": [extract_tournament(client, tournament_id, club_name)]}
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    logger.info("Guardado en %s", output_path)


def should_sync_tournament(t: Tournament, edition_filter: str | None = "CLAUSURA", season: str = "2026") -> bool:
    """
    Determina si un torneo debe sincronizarse según la temporada y la etapa del año.
    - Para 2026: omite Torneo Apertura (ya finalizado), sincroniza Clausura + Ligas Femenina Nacional / Federal.
    - Para 2027: sincroniza Apertura (inicialmente no hay Clausura) + Liga Sub 17 + Campeonato Argentino.
    """
    name_upper = (t.name or "").upper()

    if edition_filter and edition_filter.upper() == "ALL":
        return True

    if season == "2026":
        # 1. Torneos Metropolitanos: Solo Clausura (omite Apertura ya finalizado)
        if "CLAUSURA" in name_upper:
            return True
        # 2. Competencias Nacionales pendientes/faltantes: Liga Femenina Nacional y Liga Femenina Federal
        if any(keyword in name_upper for keyword in ["LIGA NACIONAL FEMENIN", "LIGA FEMENINA", "LIGA FEDERAL", "FEDERAL FEMENIN", "NACIONAL MAYORES"]):
            return True
        if edition_filter and edition_filter.upper() == "APERTURA" and "APERTURA" in name_upper:
            return True
        return False

    elif season == "2027":
        # Año 2027: Comienza con Apertura + Liga Sub 17 + Campeonato Argentino
        if "APERTURA" in name_upper:
            return True
        if "SUB 17" in name_upper and "LIGA" in name_upper:
            return True
        if "ARGENTINO" in name_upper:
            return True
        return False

    return True



def run_by_manager(
    client: ClupikClient,
    manager_id: int,
    club_name: str,
    output_path: Path,
    include_all: bool = False,
    edition_filter: str | None = "CLAUSURA",
    season: str = "2026",
) -> None:
    logger.info("Descargando listado de torneos del manager %s...", manager_id)
    tournaments = parse_tournament_list(client.get_tournament_list(manager_id))
    logger.info("Encontrados %s torneos en la Federación/Manager.", len(tournaments))

    # Filtrar según directiva (Clausura + Nacionales en 2026 para máxima velocidad)
    target_tournaments = [t for t in tournaments if should_sync_tournament(t, edition_filter, season)]
    logger.info("Torneos objetivo a sincronizar (%s/%s):", len(target_tournaments), len(tournaments))
    for t in target_tournaments:
        logger.info("  * %s (id=%s, %s)", t.name, t.clupik_id, t.status)

    result: dict = {"club": club_name, "manager_id": manager_id, "tournaments": []}

    for t in target_tournaments:
        logger.info("Verificando participación en %s (id=%s)...", t.name, t.clupik_id)
        try:
            if include_all:
                result["tournaments"].append(
                    extract_tournament(client, t.clupik_id, club_name, status=t.status)
                )
            else:
                participates, base_html, phase_cache = check_club_participation(client, t, club_name)
                if participates:
                    logger.info("  -> %s participa en %s. Descargando detalle completo...", club_name, t.name)
                    result["tournaments"].append(
                        extract_tournament(
                            client,
                            t.clupik_id,
                            club_name,
                            base_html=base_html,
                            phase_cache=phase_cache,
                            status=t.status,
                        )
                    )
                else:
                    logger.info("  -> %s no participa, se omite.", club_name)
        except Exception as exc:  # no dejamos que un torneo roto tire abajo todo el batch
            logger.warning("  -> error procesando torneo %s: %s", t.clupik_id, exc)

    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    logger.info(
        "Guardado en %s (%s torneos sincronizados para %s)",
        output_path, len(result["tournaments"]), club_name,
    )



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tournament-id", type=int, help="ID de un torneo puntual de Clupik")
    group.add_argument("--manager-id", type=int, help="ID del manager/federación; descubre los torneos automáticamente")
    parser.add_argument("--club", type=str, default="SITAS")
    parser.add_argument("--include-all", action="store_true", help="Descarga todos los torneos del manager")
    parser.add_argument("--output", type=Path, default=Path("sitas_data.json"))
    args = parser.parse_args()

    client = ClupikClient()

    if args.tournament_id:
        run_by_tournament(client, args.tournament_id, args.club, args.output)
    else:
        run_by_manager(client, args.manager_id, args.club, args.output, include_all=args.include_all)
