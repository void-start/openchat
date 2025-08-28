from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import sqlite3
import uuid
import os
import shutil
import hashlib

app = FastAPI()

# --- Конфигурация ---
DB_FILE = "db.sqlite"
ADMIN_PASSWORD = "admin123"   # пароль админки
STATIC_DIR = "static"
INDEX_FILE = os.path.join(STATIC_DIR, "index.html")
MEDIA_DIR = "media"
os.makedirs(MEDIA_DIR, exist_ok=True)

# --- Статика ---
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

# --- Инициализация БД ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE,
        password_hash TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        recipient TEXT,
        text TEXT,
        created_at INTEGER DEFAULT (strftime('%s','now'))
    )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Утилиты ---
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# --- Корень ---
@app.get("/")
async def root():
    return FileResponse(INDEX_FILE)

# --- Регистрация ---
@app.post("/register")
async def register(req: Request):
    data = await req.json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return JSONResponse({"error": "Missing fields"}, status_code=400)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        user_id = str(uuid.uuid4())
        c.execute("INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
                  (user_id, username, hash_password(password)))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return JSONResponse({"error": "Username already exists"}, status_code=400)

    conn.close()
    return {"user_id": user_id, "username": username}

# --- Логин ---
@app.post("/login")
async def login(req: Request):
    data = await req.json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return JSONResponse({"error": "Missing fields"}, status_code=400)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, password_hash FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()

    if not row or row[1] != hash_password(password):
        return JSONResponse({"error": "Invalid username or password"}, status_code=403)

    return {"user_id": row[0], "username": username}

# --- Получить пользователя ---
@app.get("/user/{user_id}")
async def get_user(user_id: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, username FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return JSONResponse({"error": "User not found"}, status_code=404)
    return {"id": row[0], "username": row[1]}

# --- Отправка текста ---
@app.post("/send")
async def send(req: Request):
    data = await req.json()
    sender = data.get("sender")
    recipient = data.get("recipient")
    text = data.get("text")
    if not (sender and recipient and text):
        return JSONResponse({"error": "Missing fields"}, status_code=400)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO messages (sender, recipient, text) VALUES (?, ?, ?)", (sender, recipient, text))
    conn.commit()
    conn.close()
    return {"status": "ok"}

# --- Отправка файла ---
@app.post("/send_file")
async def send_file(sender: str = Form(...), recipient: str = Form(...), file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4()}{ext}"
    path = os.path.join(MEDIA_DIR, filename)
    with open(path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO messages (sender, recipient, text) VALUES (?, ?, ?)",
              (sender, recipient, f"[file]{filename}"))
    conn.commit()
    conn.close()
    return {"status": "ok", "filename": filename}

# --- Inbox ---
@app.get("/inbox/{user_id}")
async def inbox(user_id: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT sender, recipient, text, created_at 
        FROM messages 
        WHERE sender=? OR recipient=? 
        ORDER BY id ASC
    """, (user_id, user_id))
    rows = c.fetchall()
    conn.close()
    return [{"sender": r[0], "recipient": r[1], "text": r[2], "created_at": r[3]} for r in rows]

# --- Админка: вход ---
@app.post("/admin/login")
async def admin_login(req: Request):
    data = await req.json()
    password = data.get("password")
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error": "Wrong admin password"}, status_code=403)
    return {"status": "ok"}

# --- Админка: список пользователей ---
@app.get("/admin/users")
async def admin_users(password: str):
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT username, password_hash FROM users ORDER BY username ASC")
    rows = c.fetchall()
    conn.close()
    return [{"username": r[0], "password_hash": r[1]} for r in rows]

# --- Админка: сброс ---
@app.post("/admin/reset")
async def admin_reset(req: Request):
    data = await req.json()
    password = data.get("password")
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM users")
    c.execute("DELETE FROM messages")
    conn.commit()
    conn.close()
    return {"status": "reset done"}
