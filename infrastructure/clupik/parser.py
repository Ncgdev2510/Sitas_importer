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


def is_playoff_phase(html: str) -> bool:
    """Verifica si el HTML corresponde a una fase de playoff / eliminatorias."""
    if not html:
        return False
    soup = BeautifulSoup(html, "html.parser")
    return soup.select_one(".playoff-viewer") is not None


def parse_playoff_bracket(
    html: str,
    tournament_id: int,
    phase_id: int | None = None,
    phase_name: str = "",
    season: str = "2026",
) -> tuple[list[Match], dict]:
    """
    Extrae los partidos y la estructura de cuadro eliminatorio desde el
    .playoff-viewer de Clupik (ej: COPA DE ORO, COPA DE PLATA, etc.).
    """
    soup = BeautifulSoup(html, "html.parser")
    playoff_viewer = soup.select_one(".playoff-viewer")
    if not playoff_viewer:
        return [], {"rounds": []}

    matches: list[Match] = []
    rounds_data: list[dict] = []

    round_elems = playoff_viewer.select(".round")
    for r_idx, r in enumerate(round_elems):
        header = r.select_one(".round-header")
        if header:
            raw_title = header.contents[0].strip() if header.contents else header.get_text(strip=True)
            round_name = raw_title.replace("\u200c", "").strip()
        else:
            round_name = f"Ronda {r_idx + 1}"

        round_dict = {
            "round_index": r_idx,
            "round_name": round_name,
            "matches": [],
        }

        for b in r.select(".bracket-container"):
            bracket_data_elem = b.select_one(".bracket-data")
            bracket_label = bracket_data_elem.get_text(strip=True) if bracket_data_elem else round_name

            # Equipos
            teams_elems = b.select(".inside .teams > .team")
            teams_info = []
            for t in teams_elems:
                t_id = t.get("data-team")
                if t_id and t_id.isdigit():
                    team_id = int(t_id)
                else:
                    href = t.get("href", "")
                    m = re.search(r"/team/(\d+)", href)
                    team_id = int(m.group(1)) if m else None

                name_text = t.get_text(strip=True)
                img_tag = t.select_one("img")
                logo_url = img_tag.get("src") if img_tag else None
                is_win = "winner" in t.get("class", [])

                teams_info.append({
                    "name": name_text,
                    "clupik_id": team_id,
                    "logo_url": logo_url,
                    "is_winner": is_win,
                })

            home_info = teams_info[0] if len(teams_info) > 0 else {"name": "Por definir", "clupik_id": None, "logo_url": None, "is_winner": False}
            away_info = teams_info[1] if len(teams_info) > 1 else {"name": "Por definir", "clupik_id": None, "logo_url": None, "is_winner": False}

            # Próximo partido (fecha/hora y sede)
            next_match = b.select_one(".next-match")
            scheduled_at = None
            venue = None
            next_match_id = None
            if next_match:
                nm_href = next_match.get("href", "")
                if nm_href:
                    m_id_match = re.search(r"/match/(\d+)", nm_href)
                    if m_id_match:
                        next_match_id = int(m_id_match.group(1))
                nm_text = next_match.get_text(" ", strip=True)
                parts = [p.strip() for p in nm_text.split("·")]
                date_part = parts[0] if len(parts) > 0 else ""
                if len(parts) > 1:
                    venue = parts[1]

                date_m = re.search(r"(\d{1,2})/(\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?", date_part)
                if date_m:
                    day, month, hour, minute = date_m.groups()
                    if hour and minute and not (day == "01" and month == "01"):
                        year = season if season and season.isdigit() else "2026"
                        try:
                            scheduled_at = datetime(int(year), int(month), int(day), int(hour), int(minute))
                        except ValueError:
                            scheduled_at = None

            # Procesar todos los partidos de la serie (.inside .matchs a.match)
            match_links = b.select(".inside .matchs a.match")
            games: list[dict] = []
            primary_match_id = None

            for g_idx, ml in enumerate(match_links):
                m_href = ml.get("href", "")
                m_id = None
                if m_href:
                    m = re.search(r"/match/(\d+)", m_href)
                    if m:
                        m_id = int(m.group(1))
                        if primary_match_id is None:
                            primary_match_id = m_id

                spans = ml.find_all("span", recursive=False)
                g_home_score = None
                g_away_score = None
                g_home_winner = False
                g_away_winner = False
                g_played = False

                if len(spans) >= 2:
                    txt0 = spans[0].get_text(strip=True)
                    txt1 = spans[1].get_text(strip=True)
                    if txt0.isdigit() and txt1.isdigit():
                        g_home_score = int(txt0)
                        g_away_score = int(txt1)
                        g_played = True
                        g_home_winner = "winner" in spans[0].get("class", []) or g_home_score > g_away_score
                        g_away_winner = "winner" in spans[1].get("class", []) or g_away_score > g_home_score

                games.append({
                    "match_id": m_id,
                    "game_number": g_idx + 1,
                    "home_score": g_home_score,
                    "away_score": g_away_score,
                    "home_winner": g_home_winner,
                    "away_winner": g_away_winner,
                    "played": g_played,
                })

                # Crear Match object para cada partido de la serie que tenga ID
                if m_id:
                    game_sched = scheduled_at if (g_idx == 0 or m_id == next_match_id) else None
                    game_venue = venue if (g_idx == 0 or m_id == next_match_id) else None
                    match_obj = Match(
                        clupik_id=m_id,
                        tournament_id=tournament_id,
                        phase_id=phase_id,
                        phase_name=phase_name,
                        round_name=round_name,
                        scheduled_at=game_sched,
                        home_club=Club(clupik_id=home_info["clupik_id"], name=home_info["name"]),
                        away_club=Club(clupik_id=away_info["clupik_id"], name=away_info["name"]),
                        home_score=g_home_score,
                        away_score=g_away_score,
                        venue=game_venue,
                        played=g_played,
                    )
                    matches.append(match_obj)

            # Si no hubo match_links pero hay next_match_id, agregar Match pendiente
            if not match_links and next_match_id:
                primary_match_id = next_match_id
                matches.append(
                    Match(
                        clupik_id=next_match_id,
                        tournament_id=tournament_id,
                        phase_id=phase_id,
                        phase_name=phase_name,
                        round_name=round_name,
                        scheduled_at=scheduled_at,
                        home_club=Club(clupik_id=home_info["clupik_id"], name=home_info["name"]),
                        away_club=Club(clupik_id=away_info["clupik_id"], name=away_info["name"]),
                        home_score=None,
                        away_score=None,
                        venue=venue,
                        played=False,
                    )
                )

            # Métricas agregadas de la serie / cruce
            is_matchup_played = any(g["played"] for g in games)
            home_wins = sum(1 for g in games if g["played"] and g["home_winner"])
            away_wins = sum(1 for g in games if g["played"] and g["away_winner"])

            # Ganador de la serie: por clase en el HTML o por victorias en partidos
            if home_info["is_winner"]:
                series_winner = "home"
            elif away_info["is_winner"]:
                series_winner = "away"
            elif home_wins >= 2 or (len(games) == 1 and home_wins == 1):
                series_winner = "home"
                home_info["is_winner"] = True
            elif away_wins >= 2 or (len(games) == 1 and away_wins == 1):
                series_winner = "away"
                away_info["is_winner"] = True
            else:
                series_winner = None

            is_matchup_finished = series_winner is not None or (len(games) == 1 and games[0]["played"])

            # Marcador representativo para compatibilidad
            if len(games) > 1 and is_matchup_played:
                home_score = home_wins
                away_score = away_wins
            elif len(games) == 1:
                home_score = games[0]["home_score"]
                away_score = games[0]["away_score"]
            else:
                home_score = None
            round_dict["matches"].append({
                "bracket_label": bracket_label,
                "match_id": primary_match_id,
                "round_name": round_name,
                "home_club": home_info,
                "away_club": away_info,
                "is_series": len(games) > 1,
                "series_winner": series_winner,
                "games": games,
                "home_score": home_score,
                "away_score": away_score,
                "played": is_matchup_played,
                "is_finished": is_matchup_finished,
                "scheduled_at": scheduled_at.strftime("%Y-%m-%d %H:%M:%S") if scheduled_at else None,
                "venue": venue,
            })

        rounds_data.append(round_dict)

    def _round_sort_weight(r_dict: dict) -> int:
        n = (r_dict.get("round_name") or "").lower().strip()
        if "32" in n:
            return 5
        if "16" in n or "diecis" in n:
            return 10
        if "octav" in n:
            return 20
        if "cuart" in n and "puesto" not in n:
            return 30
        if "semi" in n:
            return 40
        # Tercer y cuarto puesto: después de semifinal (40) y antes de final (50)
        if any(k in n for k in ["tercer", "tercero", "3er", "3°", "3º", "3ro", "bronce", "cuarto puesto", "4to puesto", "4° puesto", "4º puesto"]):
            return 45
        if "final" in n:
            return 50
        if "5" in n or "quinto" in n:
            return 60
        if "7" in n or "sept" in n or "sépt" in n:
            return 70
        if "9" in n or "noveno" in n:
            return 80
        if "11" in n:
            return 85
        if "13" in n:
            return 90
        if "15" in n:
            return 95
        return 99

    rounds_data.sort(key=_round_sort_weight)

    return matches, {"rounds": rounds_data}


def generate_playoff_standings(
    matches: list[Match],
    tournament_id: int,
    phase_id: int,
    phase_name: str,
) -> list[Standing]:
    """
    Calcula tabla de posiciones a partir de los partidos del cuadro eliminatorio.
    Determina campeón, subcampeón, 3er/4to puesto y clasificados a rondas avanzadas.
    """
    clubs_map: dict[str, Club] = {}
    stats: dict[str, dict] = {}
    round_weight = {
        "final": 100,
        "tercer": 80,
        "semi": 60,
        "cuart": 40,
        "octav": 20,
    }

    def _is_real_club(name: str) -> bool:
        n = name.lower().strip()
        if not n or "ganador" in n or "sin equipo" in n or "por definir" in n:
            return False
        return True

    def _get_weight(round_str: str) -> int:
        r = round_str.lower()
        for k, w in round_weight.items():
            if k in r:
                return w
        return 10

    for m in matches:
        for club, score, opp_score in [
            (m.home_club, m.home_score, m.away_score),
            (m.away_club, m.away_score, m.home_score),
        ]:
            if not _is_real_club(club.name):
                continue
            name = club.name.strip()
            if name not in stats:
                clubs_map[name] = club
                stats[name] = {
                    "played": 0,
                    "won": 0,
                    "lost": 0,
                    "points": 0,
                    "gf": 0,
                    "ga": 0,
                    "max_weight": 0,
                    "champion": False,
                    "runner_up": False,
                    "third": False,
                    "fourth": False,
                }

            w = _get_weight(m.round_name or "")
            if w > stats[name]["max_weight"]:
                stats[name]["max_weight"] = w

            if m.played and score is not None and opp_score is not None:
                stats[name]["played"] += 1
                stats[name]["gf"] += score
                stats[name]["ga"] += opp_score
                if score > opp_score:
                    stats[name]["won"] += 1
                    stats[name]["points"] += 2
                    if "final" in (m.round_name or "").lower() and "tercer" not in (m.round_name or "").lower():
                        stats[name]["champion"] = True
                    elif "tercer" in (m.round_name or "").lower():
                        stats[name]["third"] = True
                else:
                    stats[name]["lost"] += 1
                    stats[name]["points"] += 1
                    if "final" in (m.round_name or "").lower() and "tercer" not in (m.round_name or "").lower():
                        stats[name]["runner_up"] = True
                    elif "tercer" in (m.round_name or "").lower():
                        stats[name]["fourth"] = True

    def _sort_key(item):
        name, st = item
        podium = 10
        if st["champion"]:
            podium = 1
        elif st["runner_up"]:
            podium = 2
        elif st["third"]:
            podium = 3
        elif st["fourth"]:
            podium = 4

        return (
            podium,
            -st["max_weight"],
            -st["points"],
            -(st["gf"] - st["ga"]),
            -st["gf"],
            name,
        )

    sorted_clubs = sorted(stats.items(), key=_sort_key)
    standings: list[Standing] = []
    for pos, (name, st) in enumerate(sorted_clubs, start=1):
        standings.append(
            Standing(
                tournament_id=tournament_id,
                phase_id=phase_id,
                phase_name=phase_name,
                position=pos,
                club=clubs_map[name],
                played=st["played"],
                won=st["won"],
                drawn=0,
                lost=st["lost"],
                points=st["points"],
                goals_for=st["gf"],
                goals_against=st["ga"],
                goal_diff=st["gf"] - st["ga"],
            )
        )

    return standings


def parse_standings(html: str, tournament_id: int, phase_id: int, phase_name: str = "") -> list[Standing]:
    """
    Extrae la tabla de posiciones desde
    /es/tournament/{tournament_id}/ranking/{phase_id}.

    Soporta dos variantes de HTML de Clupik:
    1. Fase regular / grupos: tabla tradicional table.tabletype-public.
    2. Playoff / eliminatorias: cuadro visual en .playoff-viewer (Copa de Oro, Plata, etc.).
    """
    soup = BeautifulSoup(html, "html.parser")
    standings: list[Standing] = []

    # Caso 1: Tabla tradicional
    table = soup.select_one("table.tabletype-public")
    if table is not None:
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

    # Caso 2: Cuadro de Playoff / Eliminatorias (.playoff-viewer)
    if is_playoff_phase(html):
        matches, _ = parse_playoff_bracket(html, tournament_id, phase_id, phase_name)
        return generate_playoff_standings(matches, tournament_id, phase_id, phase_name)

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

            venue = None
            score_span = result_cell.select_one("span.result") if result_cell else None
            if score_span is not None:
                txt = score_span.get_text(" ", strip=True)
                m_score = re.search(r"(\d+)\s*[-–—\xa0]+\s*(\d+)", txt)
                if m_score:
                    home_score = int(m_score.group(1))
                    away_score = int(m_score.group(2))
                    played = True

            sort_holder = result_cell.select_one("[data-sort]") if result_cell else None
            if sort_holder is not None:
                raw_sort = sort_holder.get("data-sort", "").strip()
                parts = raw_sort.split()
                if len(parts) >= 3 and not parts[1].startswith("9999"):
                    try:
                        scheduled_at = datetime.strptime(
                            f"{parts[1]} {parts[2]}", "%Y-%m-%d %H:%M:%S"
                        )
                    except ValueError:
                        scheduled_at = None

            venue_span = result_cell.select_one(".ellipsis") if result_cell else None
            if venue_span:
                v_title = venue_span.get("title", "").strip()
                v_text = venue_span.get_text(strip=True)
                venue = v_title or v_text or None

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
                    venue=venue,
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
