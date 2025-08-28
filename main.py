from fastapi import FastAPI, Request, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import sqlite3
import hashlib
import os

app = FastAPI()

# --- Конфиг ---
DB_FILE = "db.sqlite"
STATIC_DIR = "static"
INDEX_FILE = os.path.join(STATIC_DIR, "index.html")
ADMIN_PASSWORD = "admin123"  # пароль для входа в админку

# --- Статика ---
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- Инициализация базы ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT
    )
    """)
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

init_db()

# --- Главная страница ---
@app.get("/")
async def root():
    return FileResponse(INDEX_FILE)

# --- Регистрация ---
@app.post("/register")
async def register(username: str = Form(...), password: str = Form(...)):
    if not username or not password:
        return JSONResponse({"error": "Missing username or password"}, status_code=400)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                  (username, hash_password(password)))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return JSONResponse({"error": "Username already exists"}, status_code=400)
    conn.close()
    return {"status": "ok", "message": "User registered"}

# --- Логин ---
@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT password_hash FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()

    if not row:
        return JSONResponse({"error": "User not found"}, status_code=404)

    if row[0] != hash_password(password):
        return JSONResponse({"error": "Invalid password"}, status_code=403)

    return {"status": "ok", "message": "Login successful"}

# --- Вход в админку ---
@app.post("/admin/login")
async def admin_login(password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error": "Wrong admin password"}, status_code=403)
    return {"status": "ok"}

# --- Список аккаунтов ---
@app.get("/admin/users")
async def list_users(password: str):
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error": "Wrong admin password"}, status_code=403)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT username, password_hash FROM users")
    rows = c.fetchall()
    conn.close()

    return [{"username": r[0], "password_hash": r[1]} for r in rows]

# --- Сброс базы ---
@app.post("/admin/reset")
async def reset(password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error": "Wrong admin password"}, status_code=403)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM users")
    conn.commit()
    conn.close()

    return {"status": "reset done"}
