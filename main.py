from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import sqlite3
import uuid

app = FastAPI()

# Разрешаем запросы с фронтенда (GitHub Pages / Render)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # можно ограничить позже
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- БД ---
def init_db():
    conn = sqlite3.connect("chat.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        display_name TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        recipient TEXT,
        text TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

# --- Модели ---
class RegisterRequest(BaseModel):
    display_name: str

class MessageRequest(BaseModel):
    sender: str
    recipient: str
    text: str

# --- API ---
@app.post("/register")
def register(req: RegisterRequest):
    user_id = str(uuid.uuid4())
    conn = sqlite3.connect("chat.db")
    c = conn.cursor()
    c.execute("INSERT INTO users (id, display_name) VALUES (?, ?)", (user_id, req.display_name))
    conn.commit()
    conn.close()
    return {"user_id": user_id}

@app.post("/send")
def send(req: MessageRequest):
    conn = sqlite3.connect("chat.db")
    c = conn.cursor()
    c.execute("INSERT INTO messages (sender, recipient, text) VALUES (?, ?, ?)",
              (req.sender, req.recipient, req.text))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/inbox/{user_id}")
def inbox(user_id: str):
    conn = sqlite3.connect("chat.db")
    c = conn.cursor()
    c.execute("SELECT sender, recipient, text FROM messages WHERE recipient=? OR sender=?",
              (user_id, user_id))
    msgs = [{"sender": s, "recipient": r, "text": t} for s, r, t in c.fetchall()]
    conn.close()
    return msgs
