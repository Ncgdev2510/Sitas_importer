"""
Parsers de HTML de Clupik -> entidades de dominio.

Selectores confirmados contra HTML real de:
  https://clupik.pro/es/tournament/1339117/ranking/3701724
(fase regular, MAXI 30, CLAUSURA 2026, Federación de Cestoball de Capital
Federal, manager_id=260550).

Todavía PENDIENTE: parse_tournament_list (no vi el HTML de
/es/manager/{id}/tournaments) y parse_calendar (no vi el HTML de
/calendar/{id}).
"""

from __future__ import annotations

import re
import sys
from datetime import datetime

from bs4 import BeautifulSoup

from domain.entities import Club, Match, Standing, Tournament


# ---------------------------------------------------------------------------
# Ranking / clasificación
# ---------------------------------------------------------------------------

def parse_tournament_metadata(html: str) -> dict:
    """
    Extrae metadata general del torneo desde el <title> y el data-path
    del <body>.

    El formato del <title> varía según la página:
      Ranking:   "Clasificación | 2026 | MAXI 30 | CLAUSURA | <Manager> | Clupik"
      Calendario: "FASE REGULAR | Calendario | 2026 | MAXI 30 | CLAUSURA | <Manager> | Clupik"
    En vez de asumir posiciones fijas, ubicamos la temporada buscando el
    primer segmento que sea un año de 4 dígitos.
    """
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else ""
    parts = [p.strip() for p in title.split("|")]

    season_idx = next(
        (i for i, p in enumerate(parts) if re.fullmatch(r"\d{4}", p)), None
    )

    tournament_id = None
    body = soup.select_one("body[data-path]")
    if body:
        match = re.search(r"/tournament/(\d+)/", body["data-path"])
        if match:
            tournament_id = int(match.group(1))

    if season_idx is None:
        return {
            "tournament_id": tournament_id,
            "season": None,
            "category": None,
            "edition": None,
            "manager_name": None,
        }

    def _get(offset: int) -> str | None:
        idx = season_idx + offset
        return parts[idx] if 0 <= idx < len(parts) else None

    return {
        "tournament_id": tournament_id,
        "season": _get(0),
        "category": _get(1),
        "edition": _get(2),
        "manager_name": _get(3),
    }


def parse_ranking_phases(html: str, tournament_id: int) -> list[dict]:
    """
    Extrae las fases del torneo (ej: FASE REGULAR, COPA DE ORO, COPA DE
    PLATA, COPA DE BRONCE) desde la barra de pestañas superior de
    /ranking. Cada fase tiene su propio phase_id, usado luego en
    /ranking/{phase_id} y /calendar/{phase_id}.
    """
    soup = BeautifulSoup(html, "html.parser")
    phases: list[dict] = []

    nav = soup.select_one("nav.bottom-bordered")
    if nav is None:
        return phases

    for a in nav.select("a[href]"):
        match = re.search(r"/ranking/(\d+)", a["href"])
        if not match:
            continue
        phases.append({
            "tournament_id": tournament_id,
            "phase_id": int(match.group(1)),
            "name": a.get_text(strip=True),
            "is_active": "active" in a.get("class", []),
        })

    return phases


def parse_standings(html: str, tournament_id: int, phase_id: int, phase_name: str = "") -> list[Standing]:
    """
    Extrae la tabla de posiciones desde
    /es/tournament/{tournament_id}/ranking/{phase_id}.

    Columnas confirmadas (en este orden): A/D, Posición, Nombre, Puntos,
    PJ, PG, PP, Valor a favor, Valor en contra, Diferencia.
    No hay columna de empates en cestoball (PJ = PG + PP).
    """
    soup = BeautifulSoup(html, "html.parser")
    standings: list[Standing] = []

    # La clase "tablestyle-XXXX" varía por torneo; "tabletype-public" es estable.
    table = soup.select_one("table.tabletype-public")
    if table is None:
        return standings

    for row in table.select("tbody tr"):
        position_cell = row.select_one("td.colstyle-posicion")
        name_cell = row.select_one("td.colstyle-nombre")
        if position_cell is None or name_cell is None:
            continue

        team_link = row.select_one("td.colstyle-ascenso-descenso a[href]")
        team_id = None
        if team_link:
            match = re.search(r"/team/(\d+)", team_link["href"])
            if match:
                team_id = int(match.group(1))

        standings.append(
            Standing(
                tournament_id=tournament_id,
                phase_id=phase_id,
                phase_name=phase_name,
                position=_parse_int(position_cell),
                club=Club(clupik_id=team_id, name=name_cell.get_text(strip=True)),
                played=_parse_int(row.select_one("td.colstyle-partidos-jugados")),
                won=_parse_int(row.select_one("td.colstyle-partidos-ganados")),
                drawn=0,
                lost=_parse_int(row.select_one("td.colstyle-partidos-perdidos")),
                points=_parse_int(row.select_one("td.colstyle-puntos")),
                goals_for=_parse_int(row.select_one("td.colstyle-valor")),
                goals_against=_parse_int(row.select_one("td.colstyle-contravalor")),
                goal_diff=_parse_int(row.select_one("td.colstyle-diferencia-valor")),
            )
        )

    return standings


def get_standing_for_club(standings: list[Standing], club_name: str) -> Standing | None:
    """Busca la fila de un club puntual (comparación case-insensitive, parcial)."""
    needle = club_name.strip().lower()
    for s in standings:
        if needle in s.club.name.strip().lower():
            return s
    return None


# ---------------------------------------------------------------------------
# Lista de torneos del manager
# ---------------------------------------------------------------------------

def parse_tournament_list(html: str) -> list[Tournament]:
    """
    Extrae la lista de torneos desde /es/manager/{manager_id}/tournaments.

    Cada fila de la tabla tiene: estado (ícono con title "Finalizada" o
    "En curso" + link a /tournament/{id}/summary), nombre, modalidad,
    temporada, categoría y sexo.
    """
    soup = BeautifulSoup(html, "html.parser")
    tournaments: list[Tournament] = []

    table = soup.select_one("table.tabletype-public")
    if table is None:
        return tournaments

    for row in table.select("tbody tr"):
        estado_cell = row.select_one("td.colstyle-estado")
        name_cell = row.select_one("td.colstyle-nombre")
        if estado_cell is None or name_cell is None:
            continue

        link = estado_cell.select_one("a[href]")
        tournament_id = None
        if link:
            m = re.search(r"/tournament/(\d+)/", link["href"])
            if m:
                tournament_id = int(m.group(1))
        if tournament_id is None:
            continue

        status_icon = estado_cell.select_one("i[title]")
        status = status_icon.get("title", "").strip() if status_icon else ""

        modalidad_cell = row.select_one("td.colstyle-modalidad")
        temporada_cell = row.select_one("td.colstyle-temporada")
        categoria_cell = row.select_one("td.colstyle-categoria")
        genero_cell = row.select_one("td.colstyle-genero")

        tournaments.append(
            Tournament(
                clupik_id=tournament_id,
                name=name_cell.get_text(strip=True),
                season=temporada_cell.get_text(strip=True) if temporada_cell else "",
                category=categoria_cell.get_text(strip=True) if categoria_cell else "",
                modality=modalidad_cell.get_text(strip=True) if modalidad_cell else "",
                sex=genero_cell.get_text(strip=True) if genero_cell else "",
                status=status,
            )
        )

    return tournaments


def find_tournaments_by_category(tournaments: list[Tournament], category: str) -> list[Tournament]:
    """Filtra torneos por categoría (comparación parcial, case-insensitive)."""
    needle = category.strip().lower()
    return [t for t in tournaments if needle in t.category.strip().lower()]


# ---------------------------------------------------------------------------
# Calendario -- PENDIENTE (falta ver el HTML real)
# ---------------------------------------------------------------------------

def parse_calendar(html: str, tournament_id: int, phase_id: int | None = None, phase_name: str = "") -> list[Match]:
    """
    Extrae los partidos desde /es/tournament/{tournament_id}/calendar/{phase_id}/all.

    El calendario está organizado en "jornadas" (rondas), cada una en su
    propia tabla dentro de un <div class="box-info full bottom-borderless">.

    Casos particulares observados en el HTML real:
    - Partidos jugados: la celda de resultado tiene
      <span class="result">102&nbsp;–&nbsp;46</span> con el marcador.
    - Partidos sin jugar todavía: no hay <span class="result">, y a veces
      la celda queda directamente vacía (fecha sentinela "9999-99-99").
    - Filas de "descanso" (bye, cuando el número de equipos es impar):
      no tienen nombre de equipo en absoluto -> se descartan.
    - La fecha/hora real vienen del atributo data-sort (formato
      "<status> <fecha> <hora> <equipo>"), no del texto visible.
    """
    soup = BeautifulSoup(html, "html.parser")
    matches: list[Match] = []

    for table in soup.select("table.tabletype-public"):
        parent_box = table.find_parent("div", class_="box-info")
        heading = parent_box.select_one("h2, h3") if parent_box else None
        round_name = heading.get_text(strip=True) if heading else None

        for row in table.select("tbody tr"):
            home_cell = row.select_one("td.colstyle-equipo-1")
            away_cell = row.select_one("td.colstyle-equipo-2")
            result_cell = row.select_one("td.colstyle-resultado")
            if home_cell is None or away_cell is None:
                continue

            home_span = home_cell.select_one("span.ellipsis[title]") or home_cell.select_one("span[title]")
            away_span = away_cell.select_one("span.ellipsis[title]") or away_cell.select_one("span[title]")

            home_name = (
                home_span.get("title", "").strip()
                if home_span
                else home_cell.get_text(strip=True).replace("Ver", "").strip()
            )
            away_name = (
                away_span.get("title", "").strip()
                if away_span
                else away_cell.get_text(strip=True).replace("Ver", "").strip()
            )

            if not home_name or not away_name:
                # Fila de descanso/bye sin equipos
                continue

            match_link = row.select_one("a[href*='/match/']")
            match_id = None
            if match_link:
                m = re.search(r"/match/(\d+)", match_link["href"])
                if m:
                    match_id = int(m.group(1))

            played = False
            home_score = None
            away_score = None
            scheduled_at = None

            score_span = result_cell.select_one("span.result") if result_cell else None
            if score_span is not None:
                numbers = re.findall(r"\d+", score_span.get_text(" ", strip=True))
                if len(numbers) >= 2:
                    home_score, away_score = int(numbers[0]), int(numbers[1])
                    played = True
            elif result_cell:
                numbers = re.findall(r"\d+", result_cell.get_text(" ", strip=True))
                if len(numbers) >= 2:
                    home_score, away_score = int(numbers[0]), int(numbers[1])
                    played = True

            sort_holder = result_cell.select_one("[data-sort]") if result_cell else None
            if sort_holder is not None:
                parts = sort_holder.get("data-sort", "").split()
                if len(parts) >= 3:
                    try:
                        scheduled_at = datetime.strptime(
                            f"{parts[1]} {parts[2]}", "%Y-%m-%d %H:%M:%S"
                        )
                    except ValueError:
                        scheduled_at = None

            matches.append(
                Match(
                    clupik_id=match_id,
                    tournament_id=tournament_id,
                    phase_id=phase_id,
                    phase_name=phase_name,
                    round_name=round_name,
                    scheduled_at=scheduled_at,
                    home_club=Club(clupik_id=None, name=home_name),
                    away_club=Club(clupik_id=None, name=away_name),
                    home_score=home_score,
                    away_score=away_score,
                    played=played,
                )
            )

    return matches


def get_matches_for_club(matches: list[Match], club_name: str) -> list[Match]:
    """Filtra los partidos donde participa un club puntual."""
    return [m for m in matches if m.involves(club_name)]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_int(cell) -> int:
    """
    Convierte celdas como "1.148" (punto = separador de miles) o "-33"
    a int. Usa el texto visible, no el atributo data-sort (que trae el
    signo negativo pegado dentro del padding de ceros y rompe int()).
    """
    if cell is None:
        return 0
    text = cell.get_text(strip=True).replace(".", "")
    try:
        return int(text)
    except ValueError:
        return 0


def _extract_id_from_href(href: str) -> int:
    match = re.search(r"(\d+)", href)
    return int(match.group(1)) if match else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python parser.py <archivo_html>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        content = f.read()

    meta = parse_tournament_metadata(content)
    print("Metadata:", meta)

    tournament_id = meta["tournament_id"] or 0
    phases = parse_ranking_phases(content, tournament_id)
    if phases:
        print("\nFases encontradas:")
        for p in phases:
            print(" -", p)

    active_phase = next((p for p in phases if p["is_active"]), phases[0] if phases else None)
    if active_phase:
        standings = parse_standings(
            content, tournament_id, active_phase["phase_id"], active_phase["name"]
        )
        if standings:
            print(f"\nClasificación ({active_phase['name']}):")
            for s in standings:
                print(f"  {s.position:2d}. {s.club.name:<20} PJ={s.played} PG={s.won} PP={s.lost} Pts={s.points} (team_id={s.club.clupik_id})")

    # Si la página es un calendario, probamos también parse_calendar.
    soup = BeautifulSoup(content, "html.parser")
    body_path = soup.select_one("body[data-path]")
    if body_path and "/calendar/" in body_path["data-path"]:
        phase_match = re.search(r"/calendar/(\d+)", body_path["data-path"])
        phase_id = int(phase_match.group(1)) if phase_match else None
        matches = parse_calendar(content, tournament_id, phase_id)
        print(f"\nPartidos encontrados: {len(matches)}")
        club = "SITAS"
        club_matches = get_matches_for_club(matches, club)
        print(f"\nPartidos de {club} ({len(club_matches)}):")
        for m in club_matches:
            fecha = m.scheduled_at.strftime("%Y-%m-%d %H:%M") if m.scheduled_at else "sin fecha"
            marcador = f"{m.home_score}-{m.away_score}" if m.played else "pendiente"
            print(f"  [{m.round_name}] {fecha} | {m.home_club.name} vs {m.away_club.name} | {marcador}")
