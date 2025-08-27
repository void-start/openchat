import os
import sqlite3
import uuid
from fastapi import FastAPI, Form, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# ----------- База данных ----------
if not os.path.exists("data"):
    os.makedirs("data")

DB_FILE = "data/chat.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        sender TEXT,
        receiver TEXT,
        type TEXT,
        content TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

# ----------- Авторизация ----------
@app.post("/register")
def register(username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        uid = str(uuid.uuid4())
        c.execute("INSERT INTO users VALUES (?, ?, ?)", (uid, username, password))
        conn.commit()
        return {"status": "ok", "user_id": uid}
    except sqlite3.IntegrityError:
        return {"status": "error", "msg": "Username taken"}
    finally:
        conn.close()

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=? AND password=?", (username, password))
    row = c.fetchone()
    conn.close()
    if row:
        return {"status": "ok", "user_id": row[0]}
    return {"status": "error", "msg": "Invalid credentials"}

# ----------- Сообщения ----------
@app.post("/send_message")
def send_message(sender: str = Form(...), receiver: str = Form(...), content: str = Form(...)):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    mid = str(uuid.uuid4())
    c.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?)", (mid, sender, receiver, "text", content))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.post("/send_file")
def send_file(sender: str = Form(...), receiver: str = Form(...), file: UploadFile = File(...)):
    ext = file.filename.split(".")[-1]
    fname = f"data/{uuid.uuid4()}.{ext}"
    with open(fname, "wb") as f:
        f.write(file.file.read())

    ftype = "video" if ext.lower() in ["mp4", "webm", "avi"] else "image"

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    mid = str(uuid.uuid4())
    c.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?)", (mid, sender, receiver, ftype, fname))
    conn.commit()
    conn.close()
    return {"status": "ok", "file": fname}

@app.get("/inbox/{user_id}")
def inbox(user_id: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT sender, type, content FROM messages WHERE receiver=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [{"sender": r[0], "type": r[1], "content": r[2]} for r in rows]

@app.get("/file/{path}")
def get_file(path: str):
    return FileResponse(path)

# ----------- WebRTC Сигнализация ----------
connections = {}

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    connections[user_id] = websocket
    try:
        while True:
            data = await websocket.receive_json()
            target_id = data.get("to")
            if target_id in connections:
                await connections[target_id].send_json({**data, "from": user_id})
    except WebSocketDisconnect:
        del connections[user_id]

# ----------- Статические файлы ----------
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def index():
    return HTMLResponse(open("static/index.html", "r", encoding="utf-8").read())
