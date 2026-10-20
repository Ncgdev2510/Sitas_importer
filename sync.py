"""
Script unificado de Sincronización y Actualización.

Ejecuta el flujo completo en un solo comando:
  1. Scraper: Descarga los últimos datos oficiales desde Clupik (con anti-bot PoW).
  2. Base de Datos: Actualiza la base relacional sitas.db con UPSERT.
  3. Frontend: Regenera web/data.json para que el dashboard refleje los cambios al instante.

Uso:
    python sync.py
    python sync.py --manager-id 260550 --club SITAS
    python sync.py --tournament-id 1339117
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from infrastructure.clupik.client import ClupikClient
from main import run_by_manager, run_by_tournament
from load_to_db import load_data_file
from infrastructure.db.queries import export_all_static_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sync")


def sync_all(
    manager_id: int = 260550,
    club_name: str = "SITAS",
    tournament_id: int | None = None,
    json_path: Path = Path("sitas_data.json"),
    db_path: Path | None = None,
    web_data_path: Path = Path("web/data.json"),
    edition: str | None = "CLAUSURA",
    season: str = "2026",
) -> None:
    start_time = time.monotonic()
    print("\n" + "=" * 60)
    print("  INICIANDO SINCRONIZACION CON CLUPIK")
    print(f"  Temporada: {season} | Edición: {edition or 'Todas'}")
    print("=" * 60)

    client = ClupikClient()

    # Paso 1: Descargar datos desde Clupik
    if tournament_id:
        logger.info("[1/3] Descargando torneo puntual %s...", tournament_id)
        run_by_tournament(client, tournament_id, club_name, json_path)
    else:
        logger.info("[1/3] Descargando torneos del manager %s para club %s (Edición: %s)...", manager_id, club_name, edition)
        run_by_manager(
            client,
            manager_id,
            club_name,
            json_path,
            include_all=False,
            edition_filter=edition,
            season=season,
        )

    # Paso 2: Cargar / Actualizar Base de Datos
    logger.info("[2/3] Actualizando base de datos relacional...")
    stats = load_data_file(json_path, db_path=db_path)

    # Paso 3: Exportar dataset estático para el frontend y GitHub Pages
    logger.info("[3/3] Exportando datos consolidados para la web (%s)...", web_data_path)
    web_data_path.parent.mkdir(exist_ok=True)
    exported = export_all_static_data(web_dir=web_data_path.parent, club_name=club_name, conn=None)
    export_path = exported["data"]

    elapsed = round(time.monotonic() - start_time, 1)
    print("\n" + "=" * 60)
    print("  SINCRONIZACION COMPLETADA EXITOSAMENTE")
    print("=" * 60)
    print(f"  - Tiempo total: {elapsed} segundos")
    print(f"  - Torneos en base de datos: {stats.get('tournaments', 0)}")
    print(f"  - Fases procesadas: {stats.get('phases', 0)}")
    print(f"  - Partidos actualizados: {stats.get('matches', 0)}")
    print(f"  - Archivo web listo: {export_path} ({export_path.stat().st_size} bytes)")
    print("  - Archivos estáticos listos para GitHub Pages en: web/")
    print("  - Dashboard disponible en: http://localhost:8000\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sincronizador unificado Clupik -> DB -> Frontend")
    parser.add_argument("--manager-id", type=int, default=260550, help="ID del manager/federación en Clupik")
    parser.add_argument("--tournament-id", type=int, default=None, help="ID de un torneo puntual (opcional)")
    parser.add_argument("--club", type=str, default="SITAS", help="Nombre del club a filtrar")
    parser.add_argument("--edition", type=str, default="CLAUSURA", help="Filtro de edición (CLAUSURA, APERTURA o ALL)")
    parser.add_argument("--season", type=str, default="2026", help="Temporada (2026, 2027)")
    parser.add_argument("--output", type=Path, default=Path("sitas_data.json"), help="Ruta del JSON intermedio")
    args = parser.parse_args()

    sync_all(
        manager_id=args.manager_id,
        club_name=args.club,
        tournament_id=args.tournament_id,
        edition=None if args.edition.upper() == "ALL" else args.edition,
        season=args.season,
        json_path=args.output,
    )

