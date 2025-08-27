from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import sqlite3
import uuid
import os

app = FastAPI()

# Конфиг
DB_FILE = "db.sqlite"
RESET_PASSWORD = "12345"  # поменяй здесь на свой пароль
INDEX_FILE = os.path.join("static", "index.html")

# Подключаем папку static
app.mount("/static", StaticFiles(directory="static"), name="static")


# --- Инициализация БД ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Пользователи
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        display_name TEXT
    )
    """)
    # Сообщения
    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        recipient TEXT,
        text TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()


# --- Роут для index.html ---
@app.get("/")
async def root():
    return FileResponse(INDEX_FILE)


# --- Регистрация ---
@app.post("/register")
async def register(req: Request):
    data = await req.json()
    display_name = data.get("display_name", "Anon")
    user_id = str(uuid.uuid4())
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO users (id, display_name) VALUES (?, ?)", (user_id, display_name))
    conn.commit()
    conn.close()
    return {"user_id": user_id, "display_name": display_name}


# --- Получить инфо о пользователе ---
@app.get("/user/{user_id}")
async def get_user(user_id: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, display_name FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return JSONResponse({"error": "User not found"}, status_code=404)
    return {"id": row[0], "display_name": row[1]}


# --- Отправка сообщений ---
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


# --- Получить все входящие ---
@app.get("/inbox/{user_id}")
async def inbox(user_id: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT sender, recipient, text FROM messages WHERE recipient=? OR sender=?", (user_id, user_id))
    rows = c.fetchall()
    conn.close()
    return [{"sender": r[0], "recipient": r[1], "text": r[2]} for r in rows]


# --- Сброс базы ---
@app.post("/reset")
async def reset(password: str):
    if password != RESET_PASSWORD:
        return JSONResponse({"error": "Wrong password"}, status_code=403)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM users")
    c.execute("DELETE FROM messages")
    conn.commit()
    conn.close()
    return {"status": "reset done"}
