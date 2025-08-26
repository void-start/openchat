from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import sqlite3
import uuid
from datetime import datetime

# ----------------- APP -----------------
app = FastAPI()

# Разрешаем CORS (для фронтенда)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Раздаём статику (фронтенд)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

# ----------------- БД -----------------
conn = sqlite3.connect("chat.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT,
    created_at TEXT
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    sender TEXT,
    recipient TEXT,
    text TEXT,
    created_at TEXT
)
""")
conn.commit()

# ----------------- MODELS -----------------
class RegisterRequest(BaseModel):
    display_name: str | None = None

class SetNameRequest(BaseModel):
    user_id: str
    display_name: str

class MessageIn(BaseModel):
    sender: str
    recipient: str
    text: str

# ----------------- API -----------------
@app.post("/register")
def register(req: RegisterRequest):
    user_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    cur.execute("INSERT INTO users (id, display_name, created_at) VALUES (?, ?, ?)",
                (user_id, req.display_name, now))
    conn.commit()
    return {"user_id": user_id, "display_name": req.display_name}

@app.post("/set_name")
def set_name(req: SetNameRequest):
    cur.execute("UPDATE users SET display_name=? WHERE id=?", (req.display_name, req.user_id))
    conn.commit()
    return {"status": "ok"}

@app.get("/users")
def list_users():
    cur.execute("SELECT id, display_name FROM users")
    rows = cur.fetchall()
    return [{"id": r[0], "display_name": r[1]} for r in rows]

@app.post("/send")
def send(msg: MessageIn):
    msg_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    cur.execute("INSERT INTO messages (id, sender, recipient, text, created_at) VALUES (?, ?, ?, ?, ?)",
                (msg_id, msg.sender, msg.recipient, msg.text, now))
    conn.commit()
    return {"status": "ok"}

@app.get("/inbox/{user_id}")
def inbox(user_id: str):
    cur.execute("SELECT sender, text, created_at FROM messages WHERE recipient=? ORDER BY created_at ASC", (user_id,))
    rows = cur.fetchall()
    return [{"sender": r[0], "text": r[1], "created_at": r[2]} for r in rows]

@app.get("/user/{user_id}")
def get_user(user_id: str):
    cur.execute("SELECT id, display_name FROM users WHERE id=?", (user_id,))
    row = cur.fetchone()
    if row:
        return {"id": row[0], "display_name": row[1]}
    return {"error": "not found"}

@app.post("/reset")
def reset():
    cur.execute("DELETE FROM users")
    cur.execute("DELETE FROM messages")
    conn.commit()
    return {"status": "ok"}



