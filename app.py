import os
import uuid
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask, abort, jsonify, redirect, render_template, request,
    send_file, session, url_for, flash
)
from werkzeug.utils import secure_filename

from firebase_config import db, verify_id_token, create_user_profile

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-secret-key")

MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", "100")) * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE


# -------------------------------------------------------------------
# Firebase Web SDK configuration
# -------------------------------------------------------------------
@app.route("/firebase-config")
def firebase_web_config():
    """Return only the Firebase Web SDK configuration needed by auth.js."""
    config = {
        "apiKey": os.getenv("FIREBASE_API_KEY", ""),
        "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN", ""),
        "projectId": os.getenv("FIREBASE_PROJECT_ID", ""),
        "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET", ""),
        "messagingSenderId": os.getenv("FIREBASE_MESSAGING_SENDER_ID", ""),
        "appId": os.getenv("FIREBASE_APP_ID", ""),
    }

    missing = [key for key, value in config.items() if not value]

    if missing:
        return jsonify({
            "error": "Firebase web configuration is incomplete.",
            "missing": missing
        }), 500

    return jsonify(config)


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def current_uid():
    return session.get("uid")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_uid():
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def get_user_folder(uid):
    folder = STORAGE_DIR / secure_filename(uid)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def get_usage(uid):
    folder = get_user_folder(uid)
    total = 0
    count = 0
    for path in folder.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
            count += 1
    return total, count


def firebase_doc(collection, doc_id):
    return db.collection(collection).document(doc_id)


def get_user_profile(uid):
    try:
        snap = firebase_doc("users", uid).get()
        return snap.to_dict() if snap.exists else {}
    except Exception:
        return {}


# -------------------------------------------------------------------
# Public pages
# -------------------------------------------------------------------
@app.route("/")
def index():
    if current_uid():
        return redirect(url_for("dashboard"))
    return render_template("index.html")


# Compatibility route for templates that use url_for("home")
@app.route("/home")
def home():
    return index()


@app.route("/login")
def login():
    if current_uid():
        return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="login")


@app.route("/register")
def register():
    if current_uid():
        return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")


# Keep compatibility with templates that use /auth
@app.route("/auth")
def auth():
    if current_uid():
        return redirect(url_for("dashboard"))
    return render_template("auth.html", mode=request.args.get("mode", "login"))


# -------------------------------------------------------------------
# Firebase client -> Flask server session
# -------------------------------------------------------------------
@app.route("/auth/session", methods=["POST"])
def auth_session():
    data = request.get_json(silent=True) or {}
    id_token = data.get("idToken")

    if not id_token:
        return jsonify({"error": "Missing Firebase ID token."}), 400

    try:
        decoded = verify_id_token(id_token)
        uid = decoded["uid"]
        email = decoded.get("email", "")
        name = decoded.get("name", "") or email.split("@")[0]

        session["uid"] = uid
        session["email"] = email
        session["name"] = name

        try:
            create_user_profile(uid, email=email, display_name=name)
        except TypeError:
            try:
                create_user_profile(uid, email, name)
            except Exception:
                pass
        except Exception:
            pass

        return jsonify({
            "success": True,
            "redirect": url_for("dashboard")
        })

    except Exception as exc:
        return jsonify({
            "error": f"Authentication failed: {exc}"
        }), 401


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -------------------------------------------------------------------
# Dashboard
# -------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    uid = current_uid()
    folder = request.args.get("folder", "").strip("/")

    root = get_user_folder(uid)
    target = root / folder

    if not target.exists() or not target.is_dir():
        folder = ""
        target = root

    items = []

    for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        rel = item.relative_to(root).as_posix()
        if item.is_dir():
            items.append({
                "name": item.name,
                "path": rel,
                "type": "folder",
                "size": 0
            })
        else:
            items.append({
                "name": item.name,
                "path": rel,
                "type": "file",
                "size": item.stat().st_size
            })

    used, file_count = get_usage(uid)
    profile = get_user_profile(uid)

    return render_template(
        "dashboard.html",
        items=items,
        current_folder=folder,
        storage_used=used,
        storage_used_mb=round(used / (1024 * 1024), 2),
        file_count=file_count,
        profile=profile,
        user={
            "email": session.get("email"),
            "name": session.get("name")
        }
    )


# -------------------------------------------------------------------
# Folder creation
# -------------------------------------------------------------------
@app.route("/folder/create", methods=["POST"])
@login_required
def create_folder():
    name = (request.form.get("name") or "").strip()
    parent = (request.form.get("parent") or "").strip("/")

    if not name:
        flash("Folder name is required.", "error")
        return redirect(url_for("dashboard", folder=parent))

    if name in {".", ".."} or "/" in name or "\\" in name:
        flash("Invalid folder name.", "error")
        return redirect(url_for("dashboard", folder=parent))

    root = get_user_folder(current_uid())
    destination = root / parent / secure_filename(name)

    try:
        destination.mkdir(parents=True, exist_ok=False)
        flash("Folder created successfully.", "success")
    except FileExistsError:
        flash("A folder with that name already exists.", "error")
    except Exception as exc:
        flash(f"Could not create folder: {exc}", "error")

    return redirect(url_for("dashboard", folder=parent))


# -------------------------------------------------------------------
# File upload
# -------------------------------------------------------------------
@app.route("/upload", methods=["POST"])
@login_required
def upload_file():
    uploaded = request.files.get("file")
    folder = (request.form.get("folder") or "").strip("/")

    if not uploaded or not uploaded.filename:
        flash("Please select a file.", "error")
        return redirect(url_for("dashboard", folder=folder))

    filename = secure_filename(uploaded.filename)
    if not filename:
        flash("Invalid filename.", "error")
        return redirect(url_for("dashboard", folder=folder))

    root = get_user_folder(current_uid())
    destination_dir = root / folder
    destination_dir.mkdir(parents=True, exist_ok=True)

    destination = destination_dir / filename

    if destination.exists():
        stem = destination.stem
        suffix = destination.suffix
        destination = destination_dir / f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"

    try:
        uploaded.save(destination)
        flash("File uploaded successfully.", "success")
    except Exception as exc:
        flash(f"Upload failed: {exc}", "error")

    return redirect(url_for("dashboard", folder=folder))


# -------------------------------------------------------------------
# Download / open
# -------------------------------------------------------------------
@app.route("/download")
@login_required
def download_file():
    relative = (request.args.get("path") or "").strip("/")
    if not relative:
        abort(400)

    root = get_user_folder(current_uid()).resolve()
    target = (root / relative).resolve()

    if root not in target.parents or not target.is_file():
        abort(404)

    return send_file(target, as_attachment=True, download_name=target.name)


@app.route("/open")
@login_required
def open_file():
    relative = (request.args.get("path") or "").strip("/")
    if not relative:
        abort(400)

    root = get_user_folder(current_uid()).resolve()
    target = (root / relative).resolve()

    if root not in target.parents or not target.is_file():
        abort(404)

    return send_file(target, as_attachment=False, download_name=target.name)


# -------------------------------------------------------------------
# Delete
# -------------------------------------------------------------------
@app.route("/delete", methods=["POST"])
@login_required
def delete_item():
    relative = (request.form.get("path") or "").strip("/")
    parent = (request.form.get("folder") or "").strip("/")

    if not relative:
        abort(400)

    root = get_user_folder(current_uid()).resolve()
    target = (root / relative).resolve()

    if root not in target.parents:
        abort(403)

    if not target.exists():
        flash("Item not found.", "error")
        return redirect(url_for("dashboard", folder=parent))

    try:
        if target.is_dir():
            # Only delete empty folders.
            target.rmdir()
        else:
            target.unlink()
        flash("Deleted successfully.", "success")
    except OSError:
        flash("Folder is not empty. Delete its contents first.", "error")
    except Exception as exc:
        flash(f"Delete failed: {exc}", "error")

    return redirect(url_for("dashboard", folder=parent))


# -------------------------------------------------------------------
# Storage API
# -------------------------------------------------------------------
@app.route("/api/storage")
@login_required
def storage_api():
    used, count = get_usage(current_uid())
    return jsonify({
        "used_bytes": used,
        "used_mb": round(used / (1024 * 1024), 2),
        "file_count": count
    })


# -------------------------------------------------------------------
# Compatibility endpoint for templates using /index
# -------------------------------------------------------------------
@app.route("/index")
def index_page():
    return index()


@app.errorhandler(413)
def too_large(_):
    flash("The selected file is too large.", "error")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
