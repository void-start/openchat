from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import uuid
import os
import hashlib
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict

app = FastAPI()

# Активные WebSocket-подключения {user_id: websocket}
active_connections: Dict[str, WebSocket] = {}

# --- Конфиг ---
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

# --- Утилиты ---
def db():
    return sqlite3.connect(DB_FILE)

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def utc_iso():
    # ISO без микросекунд, чтобы сортировка как TEXT была корректной
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

# --- Инициализация БД ---
def init_db():
    conn = db()
    c = conn.cursor()
    # пользователи
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE,
        password_hash TEXT
    )
    """)
    # сообщения
    c.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        sender_id TEXT NOT NULL,
        recipient TEXT NOT NULL,      -- 'all' или user_id получателя
        text TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    # индексы для ускорения диалогов/ленты
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_pair ON messages(sender_id, recipient)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at)")
    conn.commit()
    conn.close()

init_db()

# --- Главная ---
@app.get("/")
async def root():
    return FileResponse(INDEX_FILE)

# --- Регистрация / Логин ---
@app.post("/register")
async def register(req: Request):
    data = await req.json()
    username = data.get("login")
    password = data.get("password")
    if not username or not password:
        return JSONResponse({"error":"Missing fields"}, status_code=400)

    conn = db()
    c = conn.cursor()
    try:
        user_id = str(uuid.uuid4())
        c.execute("INSERT INTO users (id, username, password_hash) VALUES (?,?,?)",
                  (user_id, username, hash_password(password)))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return JSONResponse({"error":"Username already exists"}, status_code=400)
    conn.close()
    return {"status":"ok","user_id":user_id,"username":username}

@app.post("/login")
async def login(req: Request):
    data = await req.json()
    username = data.get("login")
    password = data.get("password")
    if not username or not password:
        return JSONResponse({"error":"Missing fields"}, status_code=400)

    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, password_hash FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()

    if not row:
        return JSONResponse({"error":"No such user"}, status_code=404)
    if row[1] != hash_password(password):
        return JSONResponse({"error":"Wrong password"}, status_code=403)

    return {"status":"ok","user_id":row[0],"username":username}

# --- Пользователи ---
@app.get("/users")
async def list_users(exclude_id: str = ""):
    conn = db()
    c = conn.cursor()
    if exclude_id:
        c.execute("SELECT id, username FROM users WHERE id <> ? ORDER BY username ASC", (exclude_id,))
    else:
        c.execute("SELECT id, username FROM users ORDER BY username ASC")
    rows = c.fetchall()
    conn.close()
    return {"users":[{"id":r[0], "username":r[1]} for r in rows]}

# --- Отправка сообщения ---
@app.post("/send")
async def send(req: Request):
    data = await req.json()
    sender_id = data.get("sender_id")
    recipient = data.get("recipient")   # 'all' или user_id
    text = (data.get("text") or "").strip()

    if not sender_id or not recipient or not text:
        return JSONResponse({"error":"Missing sender/recipient/text"}, status_code=400)

    msg_id = str(uuid.uuid4())
    created_at = utc_iso()

    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO messages (id, sender_id, recipient, text, created_at) VALUES (?,?,?,?,?)",
              (msg_id, sender_id, recipient, text, created_at))
    conn.commit()
    conn.close()
    return {"status":"sent","id":msg_id,"created_at":created_at}

# --- Получение сообщений ---
# scope=global -> общая лента
# scope=dialog&user_id={me}&peer_id={other} -> личный диалог
@app.get("/messages")
async def get_messages(scope: str = "global", user_id: str = "", peer_id: str = "", limit: int = 200):
    limit = max(1, min(limit, 500))
    conn = db()
    c = conn.cursor()

    if scope == "global":
        c.execute("""
        SELECT m.id, m.sender_id, su.username AS sender_name,
               m.recipient, NULL AS recipient_name,
               m.text, m.created_at
        FROM messages m
        LEFT JOIN users su ON su.id = m.sender_id
        WHERE m.recipient = 'all'
        ORDER BY m.created_at ASC
        LIMIT ?
        """, (limit,))
    elif scope == "dialog":
        if not user_id or not peer_id:
            conn.close()
            return JSONResponse({"error":"Missing user_id/peer_id"}, status_code=400)
        # 2-сторонний диалог
        c.execute("""
        SELECT m.id, m.sender_id, su.username AS sender_name,
               m.recipient, ru.username AS recipient_name,
               m.text, m.created_at
        FROM messages m
        LEFT JOIN users su ON su.id = m.sender_id
        LEFT JOIN users ru ON ru.id = m.recipient
        WHERE (m.sender_id = ? AND m.recipient = ?)
           OR (m.sender_id = ? AND m.recipient = ?)
        ORDER BY m.created_at ASC
        LIMIT ?
        """, (user_id, peer_id, peer_id, user_id, limit))
    else:
        conn.close()
        return JSONResponse({"error":"Unknown scope"}, status_code=400)

    rows = c.fetchall()
    conn.close()

    return [{
        "id": r[0],
        "sender_id": r[1],
        "sender_name": r[2] or r[1],
        "recipient": r[3],
        "recipient_name": r[4],
        "text": r[5],
        "created_at": r[6],
    } for r in rows]

# --- Админка ---
ADMIN_PASSWORD = "admin123"

@app.post("/admin/login")
async def admin_login(req: Request):
    data = await req.json()
    password = data.get("password")
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error":"Wrong admin password"}, status_code=403)
    return {"status":"ok"}

@app.get("/admin/users")
async def admin_users(password: str):
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error":"Forbidden"}, status_code=403)
    conn = db()
    c = conn.cursor()
    c.execute("""
    SELECT u.id, u.username, COUNT(m.id) as msg_count
    FROM users u
    LEFT JOIN messages m ON m.sender_id = u.id
    GROUP BY u.id, u.username
    ORDER BY u.username
    """)
    rows = c.fetchall()
    conn.close()
    return {"users":[{"id":r[0], "username":r[1], "messages":r[2]} for r in rows]}

@app.post("/admin/reset")
async def admin_reset(req: Request):
    data = await req.json()
    password = data.get("password")
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error":"Wrong admin password"}, status_code=403)
    conn = db()
    c = conn.cursor()
    c.execute("DELETE FROM messages")
    c.execute("DELETE FROM users")
    conn.commit()
    conn.close()
    return {"status":"reset done"}

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    active_connections[user_id] = websocket
    try:
        while True:
            data = await websocket.receive_json()
            # Ожидаем данные вида {"to":"peer_id", "type":"offer/answer/candidate", "data":{...}}
            peer_id = data.get("to")
            if peer_id in active_connections:
                await active_connections[peer_id].send_json({
                    "from": user_id,
                    "type": data["type"],
                    "data": data["data"]
                })
    except WebSocketDisconnect:
        del active_connections[user_id]