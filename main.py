from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import uuid
import os
import hashlib

app = FastAPI()

# --- Конфигурация ---
DB_FILE = "db.sqlite"
STATIC_DIR = "static"
INDEX_FILE = os.path.join(STATIC_DIR, "index.html")
os.makedirs(STATIC_DIR, exist_ok=True)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Статика ---
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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
    conn.commit()
    conn.close()

init_db()

# --- Утилита ---
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
    username = data.get("login")
    password = data.get("password")
    if not username or not password:
        return JSONResponse({"error":"Missing fields"}, status_code=400)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        user_id = str(uuid.uuid4())
        c.execute("INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
                  (user_id, username, hash_password(password)))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return JSONResponse({"error":"Username already exists"}, status_code=400)
    conn.close()
    return {"status":"ok","user_id":user_id,"username":username}

# --- Логин ---
@app.post("/login")
async def login(req: Request):
    data = await req.json()
    username = data.get("login")
    password = data.get("password")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, password_hash FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()

    if not row:
        return JSONResponse({"error":"No such user"}, status_code=404)
    if row[1] != hash_password(password):
        return JSONResponse({"error":"Wrong password"}, status_code=403)

    return {"status":"ok","user_id":row[0],"username":username}

# --- Сообщения (заглушки) ---
MESSAGES = []

@app.get("/inbox")
async def inbox():
    return MESSAGES

@app.post("/send")
async def send(req: Request):
    data = await req.json()
    recipient = data.get("recipient", "all")
    text = data.get("text", "")
    msg = {"sender":"system","recipient":recipient,"text":text}
    MESSAGES.append(msg)
    return {"status":"sent"}

# --- Админ вход ---
ADMIN_PASSWORD = "admin123"

@app.post("/admin/login")
async def admin_login(req: Request):
    data = await req.json()
    password = data.get("password")
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error": "Wrong admin password"}, status_code=403)
    return {"status": "ok"}

# --- Админ список пользователей ---
@app.get("/admin/users")
async def admin_users(password: str):
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error":"Forbidden"}, status_code=403)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT username FROM users")
    rows = c.fetchall()
    conn.close()

    return {"users": [{"username": r[0]} for r in rows]}

# --- Админ сброс ---
@app.post("/admin/reset")
async def admin_reset(req: Request):
    data = await req.json()
    password = data.get("password")
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error": "Wrong admin password"}, status_code=403)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM users")
    conn.commit()
    conn.close()
    return {"status": "reset done"}
