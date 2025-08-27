from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3, hashlib, secrets, os

app = FastAPI()
DB_FILE = "chat.db"

# ---------------- Инициализация базы ----------------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    # пользователи
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT
    )
    """)
    # сессии
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        user_id TEXT,
        token TEXT
    )
    """)
    # сообщения
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        sender TEXT,
        recipient TEXT,
        text TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------- Утилиты ----------------
def get_db():
    return sqlite3.connect(DB_FILE)

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def auth(token: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM sessions WHERE token=?", (token,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(401, "Unauthorized")
    return row[0]

# ---------------- Модели ----------------
class RegisterReq(BaseModel):
    username: str
    password: str

class LoginReq(BaseModel):
    username: str
    password: str

class SendReq(BaseModel):
    recipient: str
    text: str

# ---------------- API ----------------
@app.post("/register")
def register(req: RegisterReq):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE username=?", (req.username,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(400, "Username already exists")
    user_id = secrets.token_hex(8)
    pw_hash = hash_pw(req.password)
    cur.execute("INSERT INTO users(id, username, password) VALUES(?,?,?)",
                (user_id, req.username, pw_hash))
    token = secrets.token_hex(16)
    cur.execute("INSERT INTO sessions(user_id, token) VALUES(?,?)", (user_id, token))
    conn.commit()
    conn.close()
    return {"token": token, "user_id": user_id}

@app.post("/login")
def login(req: LoginReq):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id,password FROM users WHERE username=?", (req.username,))
    row = cur.fetchone()
    if not row or row[1] != hash_pw(req.password):
        conn.close()
        raise HTTPException(401, "Invalid credentials")
    user_id = row[0]
    token = secrets.token_hex(16)
    cur.execute("INSERT INTO sessions(user_id, token) VALUES(?,?)", (user_id, token))
    conn.commit()
    conn.close()
    return {"token": token, "user_id": user_id}

@app.post("/send")
def send(req: SendReq, token: str):
    sender = auth(token)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO messages(sender,recipient,text) VALUES(?,?,?)",
                (sender, req.recipient, req.text))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/inbox")
def inbox(token: str):
    user_id = auth(token)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT sender,text FROM messages WHERE recipient=? OR sender=?",
                (user_id, user_id))
    rows = cur.fetchall()
    conn.close()
    return [{"sender": r[0], "text": r[1]} for r in rows]

