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
INDEX_HTML_PATH = WEB_DIR / "index.html"

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


def update_index_html(latest_video: dict, html_path: Path | None = None) -> bool:
    """
    Actualiza el reproductor embebido principal de index.html con el partido más reciente.
    """
    target_path = html_path or INDEX_HTML_PATH
    if not target_path.exists() or not latest_video:
        return False

    try:
        content = target_path.read_text(encoding="utf-8")
        vid_id = latest_video.get("id", "")
        title = latest_video.get("title", "Cestoball SITAS — Transmisión en Vivo")
        category = latest_video.get("category", "Transmisión Oficial")
        badge = latest_video.get("badge", "MÁS RECIENTE")

        if not vid_id:
            return False

        # 1. Actualizar iframe src y title
        def _replace_iframe(match: re.Match) -> str:
            tag = match.group(0)
            tag = re.sub(
                r'src="https://www\.youtube\.com/embed/[^"?]+(?:\?[^"]*)?"',
                f'src="https://www.youtube.com/embed/{vid_id}?rel=0"',
                tag,
            )
            tag = re.sub(
                r'title="[^"]*"',
                f'title="{title} - Cestoball SITAS"',
                tag,
            )
            return tag

        content = re.sub(
            r'<iframe\b[^>]*?id="stream-video-iframe"[^>]*?>',
            _replace_iframe,
            content,
            flags=re.IGNORECASE,
        )

        # 2. Actualizar título h3
        content = re.sub(
            r'(<h3\b[^>]*?id="stream-current-title"[^>]*?>)[^<]*(</h3>)',
            rf'\g<1>{title}\g<2>',
            content,
            flags=re.IGNORECASE,
        )

        # 3. Actualizar enlace directo a YouTube
        def _replace_link(match: re.Match) -> str:
            tag = match.group(0)
            return re.sub(
                r'href="https://www\.youtube\.com/watch\?v=[^"&]+"',
                f'href="https://www.youtube.com/watch?v={vid_id}"',
                tag,
            )

        content = re.sub(
            r'<a\b[^>]*?id="stream-yt-direct-link"[^>]*?>',
            _replace_link,
            content,
            flags=re.IGNORECASE,
        )

        # 4. Actualizar píldora de categoría
        content = re.sub(
            r'(<span\b[^>]*?id="stream-category-pill"[^>]*?>)[^<]*(</span>)',
            rf'\g<1>{category}\g<2>',
            content,
            flags=re.IGNORECASE,
        )

        # 5. Actualizar píldora de estado (badge)
        content = re.sub(
            r'(<span\b[^>]*?id="stream-status-pill"[^>]*?>\s*<i[^>]*?></i>\s*)[^<]*(</span>)',
            rf'\g<1>{badge}\g<2>',
            content,
            flags=re.IGNORECASE,
        )

        target_path.write_text(content, encoding="utf-8")
        print(f"[OK] {target_path.name} sincronizado con el último partido: {title} ({vid_id})")
        return True
    except Exception as e:
        print(f"[!] No se pudo actualizar {target_path.name}: {e}")
        return False


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

        # Sincronizar también el reproductor principal en index.html
        update_index_html(videos[0])

    except Exception as e:
        print(f"[!] Error al sincronizar transmisiones: {e}")


if __name__ == "__main__":
    update_streams_file()

