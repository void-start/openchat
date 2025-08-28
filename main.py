from fastapi import FastAPI, Request, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import uuid
import os
import hashlib
import bcrypt # Установка: pip install bcrypt

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
    # пользователи
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE,
        password_hash TEXT NOT NULL
    )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Утилита ---
# Используем bcrypt для более надежного хеширования
def hash_password(password: str) -> str:
    # bcrypt генерирует соль и хеширует пароль
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    try:
        # bcrypt верифицирует пароль с хешем
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        return False

# --- Корень ---
@app.get("/")
async def root():
    return FileResponse(INDEX_FILE)

# --- Регистрация ---
@app.post("/register")
async def register(username: str = Form(...), password: str = Form(...)):
    if not username or not password:
        return JSONResponse({"error": "Missing fields"}, status_code=400)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        user_id = str(uuid.uuid4())
        hashed_password = hash_password(password) # Хешируем пароль
        c.execute("INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
                  (user_id, username, hashed_password))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return JSONResponse({"error": "Username already exists"}, status_code=400)
    finally:
        conn.close()

    return {"status": "ok", "user_id": user_id, "username": username}

# --- Вход ---
@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, password_hash FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()

    if not row or not verify_password(password, row[1]): # Верифицируем пароль
        return JSONResponse({"error": "Invalid username or password"}, status_code=401)

    return {"status": "ok", "user_id": row[0], "username": username}

# --- Админ вход ---
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123") # Безопасное хранение пароля
ADMIN_PASSWORD_HASH = hash_password(ADMIN_PASSWORD)

@app.post("/admin/login")
async def admin_login(req: Request):
    data = await req.json()
    password = data.get("password")
    if not password or not verify_password(password, ADMIN_PASSWORD_HASH):
        return JSONResponse({"error": "Invalid password"}, status_code=401)
    return {"status": "ok"}

# --- Админ список пользователей ---
@app.get("/admin/users")
async def admin_users(password: str):
    if not verify_password(password, ADMIN_PASSWORD_HASH):
        return JSONResponse({"error": "Forbidden"}, status_code=403)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT username FROM users") # Не возвращаем хеши
    rows = c.fetchall()
    conn.close()
    return {"users": [{"username": r[0]} for r in rows]}
# --- Админ сброс ---
@app.post("/admin/reset")
async def admin_reset(req: Request):
    data = await req.json()
    password = data.get("password")
    if not password or not verify_password(password, ADMIN_PASSWORD_HASH):
        return JSONResponse({"error": "Invalid password"}, status_code=401)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM users")
    conn.commit()
    conn.close()
    return {"status": "reset done"}