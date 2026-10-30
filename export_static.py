"""
Script de Exportación Estática para SITAS Cestoball.

Genera todos los archivos JSON necesarios (data.json, upcoming.json, posts.json)
para que la web funcione de forma 100% estática, gratuita y veloz en GitHub Pages
sin requerir un backend en vivo.

Uso:
    python export_static.py
    python export_static.py --club SITAS
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from infrastructure.db.queries import export_all_static_data, get_posts, get_upcoming_matches, get_carousel_photos


def main():
    parser = argparse.ArgumentParser(description="Exporta datos estáticos para GitHub Pages")
    parser.add_argument("--club", type=str, default="SITAS", help="Nombre del club a destacar")
    parser.add_argument("--web-dir", type=Path, default=BASE_DIR / "web", help="Directorio destino de la web")
    args = parser.parse_args()

    print("=" * 60)
    print("  EXPORTANDO DATOS ESTÁTICOS PARA GITHUB PAGES")
    print(f"  Club objetivo: {args.club}")
    print(f"  Carpeta web:   {args.web_dir}")
    print("=" * 60)

    results = export_all_static_data(web_dir=args.web_dir, club_name=args.club)

    posts_count = len(get_posts(limit=100, published_only=True))
    upcoming_count = len(get_upcoming_matches(sitas_only=False))
    carousel_count = len(get_carousel_photos(active_only=True))

    streams_path = args.web_dir / "streams.json"
    streams_count = 0
    if streams_path.exists():
        try:
            import json
            with open(streams_path, "r", encoding="utf-8") as sf:
                streams_data = json.load(sf)
                streams_count = len(streams_data.get("videos", []))
        except Exception:
            pass

    print("\n[+] Archivos generados con éxito:")
    for key, path in results.items():
        size_kb = round(path.stat().st_size / 1024, 1)
        extra_info = ""
        if key == "posts":
            extra_info = f"({posts_count} noticias publicadas)"
        elif key == "upcoming":
            extra_info = f"({upcoming_count} partidos programados)"
        elif key == "carousel":
            extra_info = f"({carousel_count} fotos en carrusel)"
        print(f"    - {path.name:<16} -> {size_kb:>7} KB  {extra_info}")

    if streams_path.exists():
        size_kb = round(streams_path.stat().st_size / 1024, 1)
        print(f"    - {streams_path.name:<16} -> {size_kb:>7} KB  ({streams_count} transmisiones de YouTube)")

    print("\n[OK] Listo. Tu carpeta 'web' está 100% preparada para publicarse en GitHub Pages.")
    print("     Comandos para publicar:")
    print("       git add web/")
    print("       git commit -m \"Actualizar datos web para GitHub Pages\"")
    print("       git push\n")


if __name__ == "__main__":
    main()
