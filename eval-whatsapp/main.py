from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Optional
import json

from fastapi import Depends
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi import Query
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from sqlmodel import Field
from sqlmodel import Session
from sqlmodel import SQLModel
from sqlmodel import create_engine
from sqlmodel import select


SQLITE_URL = "sqlite:///whatsapp.db"
engine = create_engine(SQLITE_URL)


# création des tables au démarrage de l'appli
@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(lifespan=lifespan)


# dépendance injectée dans chaque route pour obtenir une session
def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


# schéma d'entrée (ce que le client envoie)
class UserCreate(SQLModel):
    name: str

# modèle ORM correspondant à la table en base
class User(UserCreate, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)


class RoomCreate(SQLModel):
    name: str

class Room(RoomCreate, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)


# table de liaison pour les abonnements utilisateur/salon
class Subscription(SQLModel, table=True):
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    room_id: int = Field(foreign_key="room.id", primary_key=True)


class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="room.id")
    user_id: int = Field(foreign_key="user.id")
    content: str
    timestamp: str


# gestion des connexions WebSocket actives par salon
class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[tuple]] = {}

    async def connect(self, ws: WebSocket, room: str, user: str):
        await ws.accept()
        self.active.setdefault(room, []).append((ws, user))

    def disconnect(self, ws: WebSocket, room: str):
        if room in self.active:
            self.active[room] = [(w, u) for w, u in self.active[room] if w != ws]

    async def broadcast(self, room: str, data: dict):
        for ws, _ in self.active.get(room, []):
            try:
                await ws.send_json(data)
            except Exception:
                pass


manager = ConnectionManager()


@app.post("/users", status_code=201)
def create_user(body: UserCreate, session: SessionDep) -> User:
    if session.exec(select(User).where(User.name == body.name)).first():
        raise HTTPException(400, "User already exists")
    user = User.model_validate(body)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@app.get("/users")
def list_users(session: SessionDep) -> list[User]:
    return session.exec(select(User).order_by(User.name)).all()


def _create_room(body: RoomCreate, session: Session) -> Room:
    if session.exec(select(Room).where(Room.name == body.name)).first():
        raise HTTPException(400, "Room already exists")
    room = Room.model_validate(body)
    session.add(room)
    session.commit()
    session.refresh(room)
    return room


@app.post("/rooms", status_code=201)
def create_room_body(body: RoomCreate, session: SessionDep) -> Room:
    return _create_room(body, session)


@app.post("/rooms/{name}", status_code=201)
def create_room_path(name: str, session: SessionDep) -> Room:
    return _create_room(RoomCreate(name=name), session)


@app.get("/rooms")
def list_rooms(session: SessionDep, user_name: Optional[str] = None):
    rooms = session.exec(select(Room).order_by(Room.name)).all()

    if not user_name:
        return [{"id": r.id, "name": r.name, "subscribed": False} for r in rooms]

    user = session.exec(select(User).where(User.name == user_name)).first()
    if not user:
        raise HTTPException(404, "User not found")

    # on récupère les ids des salons auxquels l'utilisateur est abonné
    subs = session.exec(select(Subscription).where(Subscription.user_id == user.id)).all()
    sub_ids = {s.room_id for s in subs}

    return [{"id": r.id, "name": r.name, "subscribed": r.id in sub_ids} for r in rooms]


@app.post("/rooms/{room_name}/subscribe")
def subscribe(room_name: str, body: UserCreate, session: SessionDep):
    room = session.exec(select(Room).where(Room.name == room_name)).first()
    user = session.exec(select(User).where(User.name == body.name)).first()
    if not room or not user:
        raise HTTPException(404, "Room or user not found")

    already = session.exec(
        select(Subscription).where(Subscription.user_id == user.id, Subscription.room_id == room.id)
    ).first()
    if already:
        return {"status": "already_subscribed"}

    session.add(Subscription(user_id=user.id, room_id=room.id))
    session.commit()
    return {"status": "subscribed"}


@app.post("/rooms/{room_name}/unsubscribe")
def unsubscribe(room_name: str, body: UserCreate, session: SessionDep):
    room = session.exec(select(Room).where(Room.name == room_name)).first()
    user = session.exec(select(User).where(User.name == body.name)).first()
    if not room or not user:
        raise HTTPException(404, "Room or user not found")

    sub = session.exec(
        select(Subscription).where(Subscription.user_id == user.id, Subscription.room_id == room.id)
    ).first()
    if sub:
        session.delete(sub)
        session.commit()
    return {"status": "unsubscribed"}


@app.get("/rooms/{room_name}/messages")
def get_messages(room_name: str, session: SessionDep):
    room = session.exec(select(Room).where(Room.name == room_name)).first()
    if not room:
        raise HTTPException(404, "Room not found")

    messages = session.exec(
        select(Message).where(Message.room_id == room.id).order_by(Message.timestamp)
    ).all()

    # on joint manuellement avec User pour récupérer le nom de l'auteur
    result = []
    for msg in messages:
        user = session.get(User, msg.user_id)
        result.append({
            "id": msg.id,
            "content": msg.content,
            "timestamp": msg.timestamp,
            "user_name": user.name if user else "inconnu",
        })
    return result


@app.websocket("/ws/{room_name}")
async def chat(websocket: WebSocket, room_name: str, user_name: str = Query(...)):
    # on vérifie que le salon et l'utilisateur existent avant d'accepter la connexion
    with Session(engine) as session:
        room = session.exec(select(Room).where(Room.name == room_name)).first()
        user = session.exec(select(User).where(User.name == user_name)).first()

    if not room or not user:
        await websocket.close(code=1008)
        return

    room_id, user_id = room.id, user.id
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
            with Session(engine) as session:
                session.add(Message(room_id=room_id, user_id=user_id, content=content, timestamp=ts))
                session.commit()

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


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    with open("static/index.html") as f:
        return HTMLResponse(f.read())
