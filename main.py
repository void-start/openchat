import os
import uuid
import sqlite3
import shutil
from typing import Dict

from fastapi import FastAPI, Request, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# ----- CONFIG -----
DB_FILE = "chat.db"
STATIC_DIR = "static"
INDEX_FILE = os.path.join(STATIC_DIR, "index.html")
MEDIA_DIR = "media"
RESET_PASSWORD = os.getenv("RESET_PASSWORD", "12345")  # replace or set env var

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

# ----- APP -----
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # limit in prod
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# serve static and media
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


# ----- DB helpers -----
def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        display_name TEXT UNIQUE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT,
        recipient TEXT,
        text TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

init_db()


# ----- Serve index at root -----
@app.get("/", response_class=FileResponse)
async def root():
    # return index.html if exists, otherwise 404
    if os.path.exists(INDEX_FILE):
        return FileResponse(INDEX_FILE)
    return JSONResponse({"error": "index not found"}, status_code=404)


# ----- Auth (login creates user if not exists) -----
@app.post("/login")
async def login(req: Request):
    """
    expects JSON: {"display_name": "Nick"}
    returns: {"user_id": "...", "display_name": "..."}
    """
    data = await req.json()
    display_name = data.get("display_name")
    if not display_name:
        return JSONResponse({"error": "display_name required"}, status_code=400)

    conn = get_conn()
    cur = conn.cursor()
    # find existing
    cur.execute("SELECT id, display_name FROM users WHERE display_name=?", (display_name,))
    row = cur.fetchone()
    if row:
        user_id = row["id"]
    else:
        user_id = str(uuid.uuid4())
        cur.execute("INSERT INTO users (id, display_name) VALUES (?, ?)", (user_id, display_name))
        conn.commit()
    conn.close()
    return {"user_id": user_id, "display_name": display_name}


@app.get("/user/{user_id}")
async def get_user(user_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, display_name FROM users WHERE id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return JSONResponse({"error": "User not found"}, status_code=404)
    return {"id": row["id"], "display_name": row["display_name"]}


# ----- Sending messages (text) -----
@app.post("/send")
async def send(req: Request):
    data = await req.json()
    sender = data.get("sender")
    recipient = data.get("recipient")
    text = data.get("text")
    if not sender or not recipient or text is None:
        return JSONResponse({"error": "Missing fields"}, status_code=400)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO messages (sender, recipient, text) VALUES (?, ?, ?)", (sender, recipient, text))
    conn.commit()
    conn.close()

    # try to send to connected websocket chat if present
    if sender in ws_chat_connections:
        # nothing (sender doesn't need immediate push)
        pass
    # notify recipient if online
    ws = ws_chat_connections.get(recipient)
    if ws:
        try:
            await ws.send_json({"sender": sender, "recipient": recipient, "text": text})
        except Exception:
            # ignore send errors
            pass

    return {"status": "ok"}


# ----- File upload endpoint (multipart) -----
@app.post("/send_file")
async def send_file(
    sender: str = Form(...),
    recipient: str = Form(...),
    file: UploadFile = File(...)
):
    # Save file to MEDIA_DIR with unique name
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(MEDIA_DIR, filename)
    with open(path, "wb") as f:
        shutil = file.file.read()  # read bytes
        f.write(shutil)

    text_marker = f"[file]{filename}"

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO messages (sender, recipient, text) VALUES (?, ?, ?)", (sender, recipient, text_marker))
    conn.commit()
    conn.close()

    # push to recipient websocket if online
    ws = ws_chat_connections.get(recipient)
    if ws:
        try:
            await ws.send_json({"sender": sender, "recipient": recipient, "text": text_marker})
        except Exception:
            pass

    return {"status": "ok", "filename": filename, "url": f"/media/{filename}"}


# ----- Inbox -----
@app.get("/inbox/{user_id}")
async def inbox(user_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT sender, recipient, text, created_at
        FROM messages
        WHERE sender=? OR recipient=?
        ORDER BY id ASC
    """, (user_id, user_id))
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({
            "sender": r["sender"],
            "recipient": r["recipient"],
            "text": r["text"],
            "created_at": r["created_at"]
        })
    return result


# ----- Reset DB -----
@app.post("/reset")
async def reset(password: str = Form(...)):
    if password != RESET_PASSWORD:
        return JSONResponse({"error": "Wrong password"}, status_code=403)
    # drop tables by recreating file
    try:
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
        init_db()
        return {"status": "reset done"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ----- WebSocket handling -----
# Keep simple maps of connections, key = user_id
ws_chat_connections: Dict[str, WebSocket] = {}
ws_rtc_connections: Dict[str, WebSocket] = {}


@app.websocket("/ws/chat/{user_id}")
async def websocket_chat(websocket: WebSocket, user_id: str):
    """
    Simple websocket used for live chat notifications/messages.
    Message format expected from client: {"to": "<user_id>", "text": "hello"}
    Server forwards JSON {"sender": "...", "recipient": "...", "text": "..."}
    """
    await websocket.accept()
    ws_chat_connections[user_id] = websocket
    try:
        while True:
            data = await websocket.receive_json()
            # expecting {"to": "...", "text": "..."}
            to = data.get("to")
            text = data.get("text")
            sender = user_id
            # store in DB
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("INSERT INTO messages (sender, recipient, text) VALUES (?, ?, ?)", (sender, to, text))
            conn.commit()
            conn.close()
            # forward to recipient if connected
            ws = ws_chat_connections.get(to)
            payload = {"sender": sender, "recipient": to, "text": text}
            if ws:
                try:
                    await ws.send_json(payload)
                except Exception:
                    pass
    except WebSocketDisconnect:
        # remove
        ws_chat_connections.pop(user_id, None)


@app.websocket("/ws/rtc/{user_id}")
async def websocket_rtc(websocket: WebSocket, user_id: str):
    """
    WebRTC signaling websocket. Forward messages between peers.
    Expected messages: JSON like {"to": "<user_id>", "type": "offer"/"answer"/"candidate", "sdp":..., "candidate":...}
    Server will forward message (and preserve 'from' field).
    """
    await websocket.accept()
    ws_rtc_connections[user_id] = websocket
    try:
        while True:
            data = await websocket.receive_json()
            target = data.get("to")
            if not target:
                continue
            payload = {**data, "from": user_id}
            ws = ws_rtc_connections.get(target)
            if ws:
                try:
                    await ws.send_json(payload)
                except Exception:
                    pass
    except WebSocketDisconnect:
        ws_rtc_connections.pop(user_id, None)
