"""
Servidor Web y API para SITAS Cestoball & Panel Admin.
Integra Flask con SQLite, subida y parseo automático de PDF, gestión de noticias y fotos,
y sincronizador de Clupik con 0 dependencias externas pesadas.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    request,
    send_from_directory,
    session,
)
from werkzeug.utils import secure_filename

from infrastructure.db.database import get_db_connection, init_db
from infrastructure.db.queries import (
    create_post,
    update_post,
    delete_post,
    get_posts,
    get_post_by_id,
    get_upcoming_matches,
    save_upcoming_matches,
    clear_upcoming_matches,
    seed_default_admin,
    verify_user,
    get_user_by_id,
    export_data_for_frontend,
    export_upcoming_for_frontend,
    export_posts_for_frontend,
)

from infrastructure.pdf.parser import parse_schedule_pdf

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
UPLOADS_DIR = WEB_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "sitas_cestoball_secret_key_2026")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32MB max upload
ALLOWED_EXTENSIONS_IMG = {"png", "jpg", "jpeg", "webp", "gif"}
ALLOWED_EXTENSIONS_PDF = {"pdf"}

# Inicializar Base de Datos al arrancar
init_db()
seed_default_admin()


def allowed_file(filename: str, allowed_set: set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_set


def is_authenticated() -> bool:
    return "user_id" in session


# ==========================================
# Rutas de Frontend Estático
# ==========================================
@app.route("/")
def index():
    return send_from_directory(str(WEB_DIR), "index.html")


@app.route("/admin")
def admin_page():
    return send_from_directory(str(WEB_DIR), "admin.html")


@app.route("/uploads/<path:filename>")
def serve_upload(filename: str):
    return send_from_directory(str(UPLOADS_DIR), filename)


# ==========================================
# Endpoints de Autenticación
# ==========================================
@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or request.form
    username = data.get("username", "").strip()
    password = data.get("password", "")

    user = verify_user(username, password)
    if not user:
        return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]

    return jsonify({"success": True, "user": user})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Sesión cerrada correctamente"})


@app.route("/api/auth/me", methods=["GET"])
def me():
    if not is_authenticated():
        return jsonify({"authenticated": False}), 401
    user = get_user_by_id(session["user_id"])
    if not user:
        session.clear()
        return jsonify({"authenticated": False}), 401
    return jsonify({"authenticated": True, "user": user})


# ==========================================
# Endpoints de Cronograma / Próximos Partidos (PDF)
# ==========================================
@app.route("/api/schedule/upcoming", methods=["GET"])
def upcoming_schedule():
    sitas_only = request.args.get("sitas_only", "0") in ("1", "true", "True")
    division = request.args.get("division")
    matches = get_upcoming_matches(sitas_only=sitas_only, division=division)
    return jsonify({
        "count": len(matches),
        "matches": matches,
    })


@app.route("/api/schedule/upload-pdf", methods=["POST"])
def upload_pdf_schedule():
    if not is_authenticated():
        return jsonify({"error": "No autorizado. Inicie sesión como administrador."}), 401

    if "pdf" not in request.files:
        return jsonify({"error": "No se envió ningún archivo PDF"}), 400

    file = request.files["pdf"]
    if file.filename == "" or not allowed_file(file.filename, ALLOWED_EXTENSIONS_PDF):
        return jsonify({"error": "Archivo no válido. Debe ser un archivo .pdf"}), 400

    pdf_bytes = file.read()
    try:
        matches = parse_schedule_pdf(pdf_bytes)
    except Exception as e:
        return jsonify({"error": f"Error al parsear el PDF: {str(e)}"}), 422

    if not matches:
        return jsonify({"error": "No se encontraron partidos válidos en el PDF enviado."}), 422

    # Opción de publicar directamente en la base
    publish = request.form.get("publish", "1") in ("1", "true", "True")
    if publish:
        batch_id = datetime.now().strftime("import_%Y%m%d_%H%M%S")
        saved_count = save_upcoming_matches(matches, batch_id=batch_id, clear_previous=True)
        # Mantener archivo estático sincronizado para GitHub Pages
        export_upcoming_for_frontend(WEB_DIR / "upcoming.json")
    else:
        saved_count = 0

    sitas_matches = [m for m in matches if m.get("is_sitas")]

    return jsonify({
        "success": True,
        "total_parsed": len(matches),
        "sitas_matches_count": len(sitas_matches),
        "saved_to_db": saved_count,
        "matches": matches,
    })


@app.route("/api/schedule/clear", methods=["POST"])
def clear_schedule():
    if not is_authenticated():
        return jsonify({"error": "No autorizado"}), 401
    clear_upcoming_matches()
    # Mantener archivo estático sincronizado para GitHub Pages
    export_upcoming_for_frontend(WEB_DIR / "upcoming.json")
    return jsonify({"success": True, "message": "Cronograma eliminado con éxito"})


# ==========================================
# Endpoints de Noticias / Blog & Fotos
# ==========================================
@app.route("/api/posts", methods=["GET"])
def list_posts():
    limit = int(request.args.get("limit", 50))
    # Si está logueado como admin ve todos, de lo contrario sólo publicados
    published_only = not is_authenticated()
    posts = get_posts(limit=limit, published_only=published_only)
    return jsonify({"count": len(posts), "posts": posts})


@app.route("/api/posts", methods=["POST"])
def create_new_post():
    if not is_authenticated():
        return jsonify({"error": "No autorizado"}), 401

    title = request.form.get("title", "").strip()
    category = request.form.get("category", "General").strip()
    summary = request.form.get("summary", "").strip()
    content = request.form.get("content", "").strip()
    image_url = request.form.get("image_url", "").strip() or None
    published = request.form.get("published", "1") in ("1", "true", "True", True)

    if not title or not content:
        # Check JSON payload fallback
        data = request.get_json(silent=True) or {}
        title = data.get("title", "").strip()
        category = data.get("category", "General").strip()
        summary = data.get("summary", "").strip()
        content = data.get("content", "").strip()
        image_url = data.get("image_url", "").strip() or None
        published = data.get("published", True) in ("1", "true", "True", 1, True)

    if not title or not content:
        return jsonify({"error": "El título y el contenido son obligatorios"}), 400

    # Subida de imagen si se adjuntó archivo
    if "image" in request.files:
        file = request.files["image"]
        if file and file.filename and allowed_file(file.filename, ALLOWED_EXTENSIONS_IMG):
            ext = file.filename.rsplit(".", 1)[1].lower()
            safe_name = f"post_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}.{ext}"
            file_path = UPLOADS_DIR / safe_name
            file.save(str(file_path))
            image_url = f"/uploads/{safe_name}"

    author_id = session.get("user_id")
    post_id = create_post(
        title=title,
        category=category,
        summary=summary or (content[:150] + "..." if len(content) > 150 else content),
        content=content,
        image_url=image_url,
        author_id=author_id,
        published=published,
    )
    # Mantener archivo estático sincronizado para GitHub Pages
    export_posts_for_frontend(WEB_DIR / "posts.json")

    return jsonify({
        "success": True,
        "post_id": post_id,
        "message": "Publicación creada con éxito (Activa)" if published else "Borrador guardado con éxito (Inactivo)",
    })


@app.route("/api/posts/<int:post_id>", methods=["GET"])
def get_single_post(post_id: int):
    post = get_post_by_id(post_id)
    if not post:
        return jsonify({"error": "Publicación no encontrada"}), 404
    return jsonify({"success": True, "post": post})


@app.route("/api/posts/<int:post_id>", methods=["PUT", "POST"])
def update_post_route(post_id: int):
    if not is_authenticated():
        return jsonify({"error": "No autorizado"}), 401

    post = get_post_by_id(post_id)
    if not post:
        return jsonify({"error": "Publicación no encontrada"}), 404

    title = request.form.get("title", "").strip()
    category = request.form.get("category", "General").strip()
    summary = request.form.get("summary", "").strip()
    content = request.form.get("content", "").strip()
    image_url = request.form.get("image_url", "").strip() or None
    published_val = request.form.get("published")

    if not title or not content:
        data = request.get_json(silent=True) or {}
        title = data.get("title", post.get("title", "")).strip()
        category = data.get("category", post.get("category", "General")).strip()
        summary = data.get("summary", post.get("summary", "")).strip()
        content = data.get("content", post.get("content", "")).strip()
        image_url = data.get("image_url")
        published_val = data.get("published")

    published = str(published_val).lower() in ("1", "true", "activo") if published_val is not None else bool(post.get("published", 1))

    # Subida de nueva imagen si se adjuntó archivo
    if "image" in request.files:
        file = request.files["image"]
        if file and file.filename and allowed_file(file.filename, ALLOWED_EXTENSIONS_IMG):
            ext = file.filename.rsplit(".", 1)[1].lower()
            safe_name = f"post_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}.{ext}"
            file_path = UPLOADS_DIR / safe_name
            file.save(str(file_path))
            image_url = f"/uploads/{safe_name}"

    update_post(
        post_id=post_id,
        title=title or post["title"],
        category=category or post["category"],
        summary=summary or (content[:150] + "..." if len(content) > 150 else content),
        content=content or post["content"],
        image_url=image_url,
        published=published,
    )
    # Mantener archivo estático sincronizado para GitHub Pages
    export_posts_for_frontend(WEB_DIR / "posts.json")

    return jsonify({
        "success": True,
        "message": "Publicación actualizada correctamente",
    })


@app.route("/api/posts/<int:post_id>", methods=["DELETE"])
def remove_post(post_id: int):
    if not is_authenticated():
        return jsonify({"error": "No autorizado"}), 401

    delete_post(post_id)
    # Mantener archivo estático sincronizado para GitHub Pages
    export_posts_for_frontend(WEB_DIR / "posts.json")
    return jsonify({"success": True, "message": "Publicación eliminada correctamente"})



# ==========================================
# Endpoints de Sincronización Clupik
# ==========================================
SYNC_LOCK = threading.Lock()
SYNC_STATE = {
    "running": False,
    "start_time": None,
    "season": None,
    "edition": None,
    "last_completed": None,
    "last_success": None,
    "last_error": None,
    "last_output": None,
}


@app.route("/api/sync-clupik/status", methods=["GET"])
def sync_status():
    if not is_authenticated():
        return jsonify({"error": "No autorizado"}), 401

    elapsed = 0
    if SYNC_STATE["running"] and SYNC_STATE["start_time"]:
        elapsed = int(time.time() - SYNC_STATE["start_time"])

    return jsonify({
        "running": SYNC_STATE["running"],
        "elapsed_seconds": elapsed,
        "season": SYNC_STATE["season"],
        "edition": SYNC_STATE["edition"],
        "last_completed": SYNC_STATE["last_completed"],
        "last_success": SYNC_STATE["last_success"],
        "last_error": SYNC_STATE["last_error"],
        "last_output": SYNC_STATE["last_output"],
    })


@app.route("/api/sync-clupik", methods=["POST"])
def trigger_sync():
    if not is_authenticated():
        return jsonify({"error": "No autorizado"}), 401

    edition = request.form.get("edition") or (request.get_json(silent=True) or {}).get("edition", "CLAUSURA")
    season = request.form.get("season") or (request.get_json(silent=True) or {}).get("season", "2026")

    with SYNC_LOCK:
        if SYNC_STATE["running"]:
            elapsed = int(time.time() - (SYNC_STATE["start_time"] or time.time()))
            return jsonify({
                "success": False,
                "error": "Ya se está ejecutando una sincronización con Clupik en este momento.",
                "running": True,
                "elapsed_seconds": elapsed,
                "season": SYNC_STATE["season"],
                "edition": SYNC_STATE["edition"],
            }), 409

        SYNC_STATE["running"] = True
        SYNC_STATE["start_time"] = time.time()
        SYNC_STATE["season"] = season
        SYNC_STATE["edition"] = edition
        SYNC_STATE["last_error"] = None
        SYNC_STATE["last_output"] = None

    try:
        # Ejecutamos sync.py en un subproceso con los filtros optimizados
        cmd = [
            sys.executable,
            str(BASE_DIR / "sync.py"),
            "--edition", edition,
            "--season", season,
        ]
        result = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            SYNC_STATE["last_success"] = True
            SYNC_STATE["last_output"] = result.stdout
            SYNC_STATE["last_completed"] = datetime.now().isoformat()
            return jsonify({
                "success": True,
                "message": f"Sincronización {season} ({edition}) completada con éxito.",
                "output": result.stdout,
                "timestamp": datetime.now().isoformat(),
            })
        else:
            err_details = result.stderr or result.stdout
            SYNC_STATE["last_success"] = False
            SYNC_STATE["last_error"] = err_details
            SYNC_STATE["last_completed"] = datetime.now().isoformat()
            return jsonify({
                "success": False,
                "error": "Falló la sincronización con Clupik",
                "details": err_details,
            }), 500
    except subprocess.TimeoutExpired:
        err_msg = "Tiempo de espera agotado al sincronizar con Clupik"
        SYNC_STATE["last_success"] = False
        SYNC_STATE["last_error"] = err_msg
        SYNC_STATE["last_completed"] = datetime.now().isoformat()
        return jsonify({"success": False, "error": err_msg}), 504
    except Exception as e:
        err_msg = str(e)
        SYNC_STATE["last_success"] = False
        SYNC_STATE["last_error"] = err_msg
        SYNC_STATE["last_completed"] = datetime.now().isoformat()
        return jsonify({"success": False, "error": err_msg}), 500
    finally:
        SYNC_STATE["running"] = False



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print("==================================================")
    print("  [*] SITAS Cestoball Web & Panel Server")
    print(f"  [>] Portal Web:    http://127.0.0.1:{port}/")
    print(f"  [>] Panel Admin:  http://127.0.0.1:{port}/admin")
    print("  [i] Usuario: admin  | Password: sitas2026")
    print("==================================================")
    app.run(host="0.0.0.0", port=port, debug=True)

