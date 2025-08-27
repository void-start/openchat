import os
import uuid
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Разрешаем фронтенд подключаться
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === ХРАНИЛКИ ДАННЫХ ===
users = {}         # {username: {"password": str, "id": str}}
connections = {}   # {user_id: websocket} для чата
rtc_connections = {}  # {user_id: websocket} для WebRTC
messages = {}      # {user_id: [ {from, text/file} ]}

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# === АУТЕНТИФИКАЦИЯ ===
@app.post("/register")
async def register(username: str = Form(...), password: str = Form(...)):
    if username in users:
        return {"error": "User already exists"}
    user_id = str(uuid.uuid4())
    users[username] = {"password": password, "id": user_id}
    messages[user_id] = []
    return {"id": user_id, "username": username}

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    if username not in users:
        return {"error": "User not found"}
    if users[username]["password"] != password:
        return {"error": "Wrong password"}
    return {"id": users[username]["id"], "username": username}

# === ЗАГРУЗКА ФАЙЛОВ ===
@app.post("/send_file")
async def send_file(
    sender_id: str = Form(...),
    receiver_id: str = Form(...),
    file: UploadFile = File(...)
):
    filename = f"{uuid.uuid4()}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(await file.read())

    msg = {"from": sender_id, "file": f"/uploads/{filename}"}
    messages[receiver_id].append(msg)

    if receiver_id in connections:
        await connections[receiver_id].send_json(msg)

    return {"success": True, "file": f"/uploads/{filename}"}

@app.get("/uploads/{filename}")
async def get_file(filename: str):
    return FileResponse(os.path.join(UPLOAD_DIR, filename))

# === ВЕБСОКЕТ ДЛЯ ЧАТА ===
@app.websocket("/ws/chat/{user_id}")
async def chat_ws(websocket: WebSocket, user_id: str):
    await websocket.accept()
    connections[user_id] = websocket
    try:
        while True:
            data = await websocket.receive_json()
            # {"to": "id", "text": "..."}
            receiver_id = data.get("to")
            msg = {"from": user_id, "text": data.get("text")}
            if receiver_id in messages:
                messages[receiver_id].append(msg)
            if receiver_id in connections:
                await connections[receiver_id].send_json(msg)
    except WebSocketDisconnect:
        del connections[user_id]

# === ВЕБСОКЕТ ДЛЯ ВИДЕОЗВОНКОВ (WebRTC сигнализация) ===
@app.websocket("/ws/rtc/{user_id}")
async def rtc_ws(websocket: WebSocket, user_id: str):
    await websocket.accept()
    rtc_connections[user_id] = websocket
    try:
        while True:
            data = await websocket.receive_json()
            # {"to": "id", "type": "offer/answer/candidate", ...}
            target_id = data.get("to")
            if target_id in rtc_connections:
                await rtc_connections[target_id].send_json({**data, "from": user_id})
    except WebSocketDisconnect:
        del rtc_connections[user_id]

# === ИНБОКС ===
@app.get("/inbox/{user_id}")
async def get_inbox(user_id: str):
    return messages.get(user_id, [])
