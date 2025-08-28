from flask import Flask, request, jsonify, send_from_directory, session, redirect
from flask_cors import CORS
from flask_session import Session
import os, uuid

app = Flask(__name__)
CORS(app)

# --- Настройки сессий ---
app.secret_key = "super_secret_key"
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# --- БД в памяти ---
USERS = {}       # login -> {"password": "...", "id": "..."}
MESSAGES = []    # {sender, recipient, text}
MEDIA_DIR = "media"
os.makedirs(MEDIA_DIR, exist_ok=True)

ADMIN_PASSWORD = "admin123"  # пароль админки


# --- Helpers ---
def current_user():
    uid = session.get("user_id")
    for u, data in USERS.items():
        if data["id"] == uid:
            return u, data
    return None, None


# --- Маршруты авторизации ---
@app.route("/register", methods=["POST"])
def register():
    data = request.json
    login = data.get("login")
    password = data.get("password")

    if not login or not password:
        return jsonify({"error": "Missing login/password"}), 400
    if login in USERS:
        return jsonify({"error": "User exists"}), 400

    uid = str(uuid.uuid4())[:8]
    USERS[login] = {"password": password, "id": uid}
    session["user_id"] = uid
    return jsonify({"status": "registered", "user_id": uid, "login": login})


@app.route("/login", methods=["POST"])
def login():
    data = request.json
    login = data.get("login")
    password = data.get("password")

    if login not in USERS or USERS[login]["password"] != password:
        return jsonify({"error": "Invalid login/password"}), 403

    session["user_id"] = USERS[login]["id"]
    return jsonify({"status": "logged_in", "user_id": USERS[login]["id"], "login": login})


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"status": "logged_out"})


# --- Чат ---
@app.route("/send", methods=["POST"])
def send_msg():
    user, data = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 403

    body = request.json
    recipient = body.get("recipient")
    text = body.get("text", "")
    if not recipient:
        return jsonify({"error": "No recipient"}), 400

    MESSAGES.append({"sender": data["id"], "recipient": recipient, "text": text})
    return jsonify({"status": "sent"})


@app.route("/send_file", methods=["POST"])
def send_file():
    user, data = current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 403

    file = request.files["file"]
    recipient = request.form["recipient"]
    filename = str(uuid.uuid4()) + "_" + file.filename
    path = os.path.join(MEDIA_DIR, filename)
    file.save(path)
    MESSAGES.append({"sender": data["id"], "recipient": recipient, "text": "[file]" + filename})
    return jsonify({"status": "file_sent", "filename": filename})


@app.route("/media/<path:fname>")
def media(fname):
    return send_from_directory(MEDIA_DIR, fname)


@app.route("/inbox")
def inbox():
    user, data = current_user()
    if not user:
        return jsonify([])

    uid = data["id"]
    msgs = [m for m in MESSAGES if m["sender"] == uid or m["recipient"] == uid]
    return jsonify(msgs)


# --- Админка ---
@app.route("/admin_login", methods=["POST"])
def admin_login():
    pwd = request.json.get("password")
    if pwd == ADMIN_PASSWORD:
        session["is_admin"] = True
        return jsonify({"status": "ok"})
    return jsonify({"error": "wrong password"}), 403


@app.route("/admin_panel")
def admin_panel():
    if not session.get("is_admin"):
        return jsonify({"error": "not admin"}), 403
    return jsonify({"users": USERS, "messages_count": len(MESSAGES)})


@app.route("/admin_reset", methods=["POST"])
def admin_reset():
    if not session.get("is_admin"):
        return jsonify({"error": "not admin"}), 403
    USERS.clear()
    MESSAGES.clear()
    return jsonify({"status": "reset"})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
