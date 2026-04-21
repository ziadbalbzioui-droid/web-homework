"""
WhatsApp-like chat application.
FastAPI + WebSockets + SQLite
"""

import json
import sqlite3
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="WhatsApp Clone")


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect("whatsapp.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS rooms (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER NOT NULL,
            room_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, room_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id   INTEGER NOT NULL,
            user_id   INTEGER NOT NULL,
            content   TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (room_id) REFERENCES rooms(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    conn.commit()
    conn.close()


init_db()


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Tracks active WebSocket connections per room."""

    def __init__(self):
        # room_name -> list of (WebSocket, user_name)
        self.active: dict[str, list[tuple]] = {}

    async def connect(self, ws: WebSocket, room: str, user: str) -> None:
        await ws.accept()
        self.active.setdefault(room, []).append((ws, user))

    def disconnect(self, ws: WebSocket, room: str) -> None:
        if room in self.active:
            self.active[room] = [(w, u) for w, u in self.active[room] if w != ws]

    async def broadcast(self, room: str, data: dict) -> None:
        for ws, _ in self.active.get(room, []):
            try:
                await ws.send_json(data)
            except Exception:
                pass


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class NameIn(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@app.post("/users", status_code=201)
def create_user(body: NameIn):
    """Create a new user (called from the CLI)."""
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (name) VALUES (?)", (body.name,))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE name=?", (body.name,)).fetchone()
        return dict(row)
    except sqlite3.IntegrityError:
        raise HTTPException(400, "User already exists")
    finally:
        conn.close()


@app.get("/users")
def list_users():
    """Return all users sorted by name."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

def _create_room(name: str) -> dict:
    conn = get_db()
    try:
        conn.execute("INSERT INTO rooms (name) VALUES (?)", (name,))
        conn.commit()
        row = conn.execute("SELECT * FROM rooms WHERE name=?", (name,)).fetchone()
        return dict(row)
    except sqlite3.IntegrityError:
        raise HTTPException(400, "Room already exists")
    finally:
        conn.close()


@app.post("/rooms", status_code=201)
def create_room_body(body: NameIn):
    """Create a room via JSON body: http POST /rooms name=social"""
    return _create_room(body.name)


@app.post("/rooms/{name}", status_code=201)
def create_room_path(name: str):
    """Create a room via path: http POST /rooms/social"""
    return _create_room(name)


@app.get("/rooms")
def list_rooms(user_name: Optional[str] = None):
    """
    List all rooms.
    If user_name is given, each room includes a `subscribed` boolean.
    """
    conn = get_db()
    if user_name:
        user = conn.execute("SELECT id FROM users WHERE name=?", (user_name,)).fetchone()
        if not user:
            conn.close()
            raise HTTPException(404, "User not found")
        rows = conn.execute("""
            SELECT r.id, r.name,
                   CASE WHEN s.user_id IS NOT NULL THEN 1 ELSE 0 END AS subscribed
            FROM rooms r
            LEFT JOIN subscriptions s ON r.id = s.room_id AND s.user_id = ?
            ORDER BY r.name
        """, (user["id"],)).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, 0 AS subscribed FROM rooms ORDER BY name"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

@app.post("/rooms/{room_name}/subscribe")
def subscribe(room_name: str, body: NameIn):
    """Subscribe a user to a room."""
    conn = get_db()
    room = conn.execute("SELECT id FROM rooms WHERE name=?", (room_name,)).fetchone()
    user = conn.execute("SELECT id FROM users WHERE name=?", (body.name,)).fetchone()
    if not room or not user:
        conn.close()
        raise HTTPException(404, "Room or user not found")
    try:
        conn.execute("INSERT INTO subscriptions VALUES (?, ?)", (user["id"], room["id"]))
        conn.commit()
        return {"status": "subscribed"}
    except sqlite3.IntegrityError:
        return {"status": "already_subscribed"}
    finally:
        conn.close()


@app.post("/rooms/{room_name}/unsubscribe")
def unsubscribe(room_name: str, body: NameIn):
    """Unsubscribe a user from a room."""
    conn = get_db()
    room = conn.execute("SELECT id FROM rooms WHERE name=?", (room_name,)).fetchone()
    user = conn.execute("SELECT id FROM users WHERE name=?", (body.name,)).fetchone()
    if not room or not user:
        conn.close()
        raise HTTPException(404, "Room or user not found")
    conn.execute(
        "DELETE FROM subscriptions WHERE user_id=? AND room_id=?",
        (user["id"], room["id"])
    )
    conn.commit()
    conn.close()
    return {"status": "unsubscribed"}


# ---------------------------------------------------------------------------
# Messages (history)
# ---------------------------------------------------------------------------

@app.get("/rooms/{room_name}/messages")
def get_messages(room_name: str):
    """Return the full message history for a room."""
    conn = get_db()
    room = conn.execute("SELECT id FROM rooms WHERE name=?", (room_name,)).fetchone()
    if not room:
        conn.close()
        raise HTTPException(404, "Room not found")
    rows = conn.execute("""
        SELECT m.id, m.content, m.timestamp, u.name AS user_name
        FROM messages m
        JOIN users u ON m.user_id = u.id
        WHERE m.room_id = ?
        ORDER BY m.timestamp
    """, (room["id"],)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# WebSocket — real-time chat
# ---------------------------------------------------------------------------

@app.websocket("/ws/{room_name}")
async def chat(
    websocket: WebSocket,
    room_name: str,
    user_name: str = Query(...),
):
    """
    WebSocket endpoint for a room.
    Connect with: ws://host/ws/<room>?user_name=<name>
    Send JSON: {"content": "hello"}
    Receive JSON: {"type": "message"|"system", "user": ..., "content": ..., "timestamp": ...}
    """
    conn = get_db()
    room = conn.execute("SELECT id FROM rooms WHERE name=?", (room_name,)).fetchone()
    user = conn.execute("SELECT id FROM users WHERE name=?", (user_name,)).fetchone()
    conn.close()

    if not room or not user:
        await websocket.close(code=1008)  # Policy violation
        return

    room_id, user_id = room["id"], user["id"]
    await manager.connect(websocket, room_name, user_name)
    await manager.broadcast(room_name, {
        "type": "system",
        "content": f"{user_name} a rejoint le salon",
        "timestamp": datetime.now().isoformat(),
    })

    try:
        while True:
            raw = await websocket.receive_text()
            content = json.loads(raw).get("content", "").strip()
            if not content:
                continue

            ts = datetime.now().isoformat()

            conn = get_db()
            conn.execute(
                "INSERT INTO messages (room_id, user_id, content, timestamp) VALUES (?, ?, ?, ?)",
                (room_id, user_id, content, ts),
            )
            conn.commit()
            conn.close()

            await manager.broadcast(room_name, {
                "type": "message",
                "user": user_name,
                "content": content,
                "timestamp": ts,
            })

    except WebSocketDisconnect:
        manager.disconnect(websocket, room_name)
        await manager.broadcast(room_name, {
            "type": "system",
            "content": f"{user_name} a quitté le salon",
            "timestamp": datetime.now().isoformat(),
        })


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    with open("static/index.html") as f:
        return HTMLResponse(f.read())
