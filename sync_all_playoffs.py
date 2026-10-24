import json
import logging
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sync_playoffs")

from infrastructure.clupik.client import ClupikClient
from main import extract_tournament
from load_to_db import load_data_file
from infrastructure.db.queries import export_all_static_data

TOURNAMENTS_TO_SYNC = [
    # Clausura
    1339245,  # PRIMERA MASCULINO CLAUSURA
    1339244,  # PRIMERA A CLAUSURA
    1339243,  # PRIMERA B CLAUSURA
    1339117,  # MAXI 30 CLAUSURA
    1341496,  # SUB 14 CLAUSURA
    1341497,  # SUB 14 FLEX CLAUSURA
    1341498,  # SUB 17 CLAUSURA
    1341499,  # SUB 17 FLEX CLAUSURA
    1339242,  # SUB 20 CLAUSURA
    # Apertura
    1334343,  # PRIMERA MASCULINO APERTURA
    1334344,  # MAXI 30 APERTURA
    1334339,  # PRIMERA A APERTURA
    1334338,  # PRIMERA B APERTURA
    1334325,  # SUB 14 APERTURA
    1334330,  # SUB 14 FLEX APERTURA
    1334329,  # SUB 17 APERTURA
    1334331,  # SUB 17 FLEX APERTURA
    1334335,  # SUB 20 APERTURA
    # Ligas Nacionales
    1344079,  # LIGA NACIONAL MAYORES FEMENINA
    1342950,  # LIGA NACIONAL PRIMERA MASCULINO
    1341999,  # LIGA NACIONAL SUB 14
    1338188,  # LIGA NACIONAL SUB 17
]

def main():
    start_time = time.monotonic()
    client = ClupikClient()

    # Cargar sitas_data.json existente para preservar torneos
    data_file = Path("sitas_data.json")
    if data_file.exists():
        root_data = json.loads(data_file.read_text(encoding="utf-8"))
    else:
        root_data = {"club": "SITAS", "tournaments": []}

    t_map = {}
    for t_item in root_data.get("tournaments", []):
        t_id = t_item.get("tournament", {}).get("tournament_id")
        if t_id:
            t_map[t_id] = t_item

    for i, t_id in enumerate(TOURNAMENTS_TO_SYNC, 1):
        logger.info("[%s/%s] Extrayendo torneo %s desde Clupik...", i, len(TOURNAMENTS_TO_SYNC), t_id)
        try:
            extracted = extract_tournament(client, t_id, "SITAS")
            t_map[t_id] = extracted
            logger.info("  -> Torneo %s extraído exitosamente (%s fases).", t_id, len(extracted.get("phases", [])))
        except Exception as e:
            logger.error("  -> Error extrayendo torneo %s: %s", t_id, e)

    # Actualizar y guardar sitas_data.json
    root_data["tournaments"] = list(t_map.values())
    data_file.write_text(json.dumps(root_data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    logger.info("sitas_data.json guardado con %s torneos.", len(root_data["tournaments"]))

    # Cargar a sitas.db con load_data_file
    logger.info("Cargando todos los torneos a la base de datos sitas.db...")
    stats = load_data_file(data_file, db_path="sitas.db")
    logger.info("Base de datos actualizada: %s", stats)

    # Regenerar archivos estáticos para la web
    logger.info("Exportando datos consolidados para web (data.json, upcoming.json, posts.json)...")
    export_all_static_data(web_dir=Path("web"), club_name="SITAS")
    logger.info("¡Sincronización completada en %.1f segundos!", time.monotonic() - start_time)

if __name__ == "__main__":
    main()
