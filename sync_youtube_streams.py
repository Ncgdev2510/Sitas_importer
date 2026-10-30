"""
Sincronizador automático de Transmisiones de YouTube para SITAS Cestoball.
Obtiene los últimos streams y videos emitidos en el canal oficial https://www.youtube.com/@sitascesto/streams
y actualiza web/streams.json.

Uso:
    python sync_youtube_streams.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
STREAMS_JSON_PATH = WEB_DIR / "streams.json"

CHANNEL_HANDLE = "@sitascesto"
CHANNEL_URL = f"https://www.youtube.com/{CHANNEL_HANDLE}"
STREAMS_URL = f"{CHANNEL_URL}/streams"


def fetch_latest_streams(max_videos: int = 6) -> list[dict]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "es-419,es;q=0.9,en;q=0.8",
    }
    req = urllib.request.Request(STREAMS_URL, headers=headers)

    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode("utf-8", "ignore")

    # Extraer video IDs únicos en orden de aparición
    vids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
    unique_vids = []
    seen = set()
    for v in vids:
        if v not in seen:
            seen.add(v)
            unique_vids.append(v)
        if len(unique_vids) >= max_videos:
            break

    videos_data = []
    for idx, vid in enumerate(unique_vids):
        # Obtener título detallado a través de oEmbed
        title = "Cestoball SITAS — Transmisión de Partido"
        badge = "MÁS RECIENTE" if idx == 0 else "TRANSMISIÓN"
        category = "Transmisión Oficial"

        try:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"
            oembed_req = urllib.request.Request(oembed_url, headers=headers)
            with urllib.request.urlopen(oembed_req, timeout=8) as oresp:
                o_data = json.loads(oresp.read().decode("utf-8", "ignore"))
                fetched_title = o_data.get("title", "").strip()
                if fetched_title:
                    title = fetched_title
        except Exception:
            pass

        # Detectar categoría o badge a partir del título
        title_lower = title.lower()
        if "sub" in title_lower or "primera" in title_lower or "infantil" in title_lower:
            if "sub 17" in title_lower or "sub17" in title_lower:
                category = "Categoría Sub-17"
            elif "sub 20" in title_lower or "sub20" in title_lower:
                category = "Categoría Sub-20"
            elif "primera" in title_lower:
                category = "Primera División"
            elif "mini" in title_lower:
                category = "Mini Cestoball"

        if "playoff" in title_lower or "cuartos" in title_lower or "semi" in title_lower or "final" in title_lower:
            badge = "PLAYOFF / DEFINICIÓN"

        videos_data.append({
            "id": vid,
            "title": title,
            "badge": badge,
            "category": category,
        })

    return videos_data


def update_streams_file() -> None:
    print(f"[*] Consultando transmisiones en {STREAMS_URL}...")
    try:
        videos = fetch_latest_streams(max_videos=5)
        if not videos:
            print("[!] No se encontraron videos automáticamente.")
            return

        latest_id = videos[0]["id"]
        data = {
            "channel_url": CHANNEL_URL,
            "streams_url": STREAMS_URL,
            "channel_name": "Cestoball SITAS",
            "handle": CHANNEL_HANDLE,
            "latest_video_id": latest_id,
            "videos": videos,
        }

        STREAMS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(STREAMS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"[OK] {STREAMS_JSON_PATH.name} actualizado con {len(videos)} transmisiones:")
        for idx, v in enumerate(videos, 1):
            print(f"     {idx}. [{v['id']}] {v['title']} ({v['badge']})")

    except Exception as e:
        print(f"[!] Error al sincronizar transmisiones: {e}")


if __name__ == "__main__":
    update_streams_file()

