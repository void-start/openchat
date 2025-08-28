import sqlite3
import hashlib
import uuid
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

DB_FILE = "users.db"
ADMIN_PASSWORD = "admin123"  # пароль для админ-панели

app = FastAPI()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Helpers ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE,
            password_hash TEXT
        )
    """)
    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

init_db()

# --- Auth routes ---
@app.post("/register")
async def register(username: str = Form(...), password: str = Form(...)):
    if not username or not password:
        return JSONResponse({"error":"Missing fields"}, status_code=400)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        user_id = str(uuid.uuid4())
        c.execute("INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
                  (user_id, username, hash_password(password)))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return JSONResponse({"error":"Username already exists"}, status_code=400)
    conn.close()
    return {"status":"ok","user_id":user_id,"username":username}

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, password_hash FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()

    if not row:
        return JSONResponse({"error":"No such user"}, status_code=404)

    if row[1] != hash_password(password):
        return JSONResponse({"error":"Wrong password"}, status_code=403)

    return {"status":"ok","user_id":row[0],"username":username}

# --- Admin routes ---
@app.post("/admin/login")
async def admin_login(password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error":"Wrong admin password"}, status_code=403)
    return {"status":"ok"}

@app.get("/admin/users")
async def admin_users(password: str):
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error":"Forbidden"}, status_code=403)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT username, password_hash FROM users")
    rows = c.fetchall()
    conn.close()

    return {"users": [{"username": r[0], "password": r[1]} for r in rows]}

@app.post("/admin/reset")
async def admin_reset(password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        return JSONResponse({"error":"Forbidden"}, status_code=403)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM users")
    conn.commit()
    conn.close()
    return {"status":"reset_ok"}

# --- Serve static index.html ---
app.mount("/", StaticFiles(directory=".", html=True), name="static")
