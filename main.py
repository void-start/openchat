import os
from fastapi import FastAPI, UploadFile, Form, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import shutil

app = FastAPI()

# --- Настройка CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Создаем папки если их нет ---
os.makedirs("static", exist_ok=True)
os.makedirs("media", exist_ok=True)

# --- Подключаем статику ---
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")

# --- Создаем БД если нет ---
def init_db():
    conn = sqlite3.connect("chat.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            display_name TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT,
            recipient TEXT,
            text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Отдаём index.html ---
@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse("static/index.html")


# --- API ---
@app.post("/login")
async def login(data: dict):
    import uuid
    user_id = str(uuid.uuid4())[:8]
    display_name = data.get("display_name", "Anon")

    conn = sqlite3.connect("chat.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (id, display_name) VALUES (?,?)", (user_id, display_name))
    conn.commit()
    conn.close()

    return {"user_id": user_id, "display_name": display_name}

@app.post("/send")
async def send(data: dict):
    conn = sqlite3.connect("chat.db")
    c = conn.cursor()
    c.execute("INSERT INTO messages (sender, recipient, text) VALUES (?,?,?)",
              (data["sender"], data["recipient"], data["text"]))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/inbox/{user_id}")
async def inbox(user_id: str):
    conn = sqlite3.connect("chat.db")
    c = conn.cursor()
    c.execute("SELECT sender, recipient, text, timestamp FROM messages WHERE recipient=? OR sender=? ORDER BY id ASC",
              (user_id, user_id))
    rows = c.fetchall()
    conn.close()
    return [{"sender": r[0], "recipient": r[1], "text": r[2], "timestamp": r[3]} for r in rows]

@app.post("/send_file")
async def send_file(sender: str = Form(...), recipient: str = Form(...), file: UploadFile = None):
    filename = file.filename
    filepath = os.path.join("media", filename)
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    conn = sqlite3.connect("chat.db")
    c = conn.cursor()
    c.execute("INSERT INTO messages (sender, recipient, text) VALUES (?,?,?)",
              (sender, recipient, f"[file]{filename}"))
    conn.commit()
    conn.close()

    return {"status": "file_sent", "filename": filename}

@app.post("/reset")
async def reset(password: str):
    if password != "12345":
        return {"error": "Invalid password"}
    if os.path.exists("chat.db"):
        os.remove("chat.db")
    init_db()
    return {"status": "Database reset successful"}
