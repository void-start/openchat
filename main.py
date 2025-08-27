from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import sqlite3
import uuid
import os
import shutil

app = FastAPI()

# --- Конфигурация ---
DB_FILE = "db.sqlite"
RESET_PASSWORD = "12345"  # смените на свой
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
        display_name TEXT UNIQUE
    )
    """)
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

# --- Корень ---
@app.get("/")
async def root():
    return FileResponse(INDEX_FILE)

# --- Login / Register ---
@app.post("/login")
async def login(req: Request):
    data = await req.json()
    display_name = data.get("display_name", "Anon")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE display_name=?", (display_name,))
    row = c.fetchone()
    if row:
        user_id = row[0]
    else:
        user_id = str(uuid.uuid4())
        c.execute("INSERT INTO users (id, display_name) VALUES (?, ?)", (user_id, display_name))
        conn.commit()
    conn.close()
    return {"user_id": user_id, "display_name": display_name}

# --- Получить пользователя ---
@app.get("/user/{user_id}")
async def get_user(user_id: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, display_name FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return JSONResponse({"error":"User not found"}, status_code=404)
    return {"id": row[0], "display_name": row[1]}

# --- Отправка текста ---
@app.post("/send")
async def send(req: Request):
    data = await req.json()
    sender = data.get("sender")
    recipient = data.get("recipient")
    text = data.get("text")
    if not (sender and recipient and text):
        return JSONResponse({"error":"Missing fields"}, status_code=400)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO messages (sender, recipient, text) VALUES (?, ?, ?)", (sender, recipient, text))
    conn.commit()
    conn.close()
    return {"status":"ok"}

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
    return {"status":"ok","filename":filename}

# --- Inbox ---
@app.get("/inbox/{user_id}")
async def inbox(user_id: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT sender, recipient, text FROM messages WHERE sender=? OR recipient=? ORDER BY id ASC", (user_id, user_id))
    rows = c.fetchall()
    conn.close()
    return [{"sender": r[0], "recipient": r[1], "text": r[2]} for r in rows]

# --- Сброс базы ---
@app.post("/reset")
async def reset(password: str):
    if password != RESET_PASSWORD:
        return JSONResponse({"error":"Wrong password"}, status_code=403)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM users")
    c.execute("DELETE FROM messages")
    conn.commit()
    conn.close()
    return {"status":"reset done"}
