# WhatsApp Clone — Évaluation

Application de chat en temps réel inspirée de WhatsApp, construite avec **FastAPI**, **WebSockets** et **SQLite**.

## Technologies

- **Backend** : FastAPI + Uvicorn
- **Temps réel** : WebSockets (natifs FastAPI)
- **Base de données** : SQLite (fichier `whatsapp.db` créé automatiquement)
- **Frontend** : HTML/CSS/JavaScript vanilla (single-page app)

## Installation

```bash
pip install "fastapi[standard]"
```

## Lancer le serveur

```bash
# Depuis le dossier eval-whatsapp/
fastapi dev main.py
```

Le serveur démarre sur `http://localhost:8000`.

## Créer des utilisateurs et des salons (CLI)

Dans un autre terminal :

```bash
# Créer des utilisateurs
http POST http://localhost:8000/users name=alice
http POST http://localhost:8000/users name=bob
http POST http://localhost:8000/users name=charlie

# Créer des salons (deux syntaxes possibles)
http POST http://localhost:8000/rooms/social
http POST http://localhost:8000/rooms/sports
http POST http://localhost:8000/rooms/bde
```

> `http` est la commande [HTTPie](https://httpie.io/). On peut aussi utiliser `curl`.

## Utiliser l'interface

1. Ouvrir `http://localhost:8000`
2. **Choisir un nom d'utilisateur** parmi ceux créés en CLI
3. **Page des salons** : s'abonner / se désabonner, puis cliquer « Entrer »
4. **Page de chat** : voir l'historique, envoyer des messages en temps réel

## API REST

| Méthode | Route | Description |
|---------|-------|-------------|
| `POST` | `/users` | Créer un utilisateur `{"name": "alice"}` |
| `GET`  | `/users` | Lister tous les utilisateurs |
| `POST` | `/rooms` | Créer un salon `{"name": "social"}` |
| `POST` | `/rooms/{name}` | Créer un salon via le path |
| `GET`  | `/rooms?user_name=alice` | Lister les salons (avec statut d'abonnement) |
| `POST` | `/rooms/{name}/subscribe` | S'abonner `{"name": "alice"}` |
| `POST` | `/rooms/{name}/unsubscribe` | Se désabonner `{"name": "alice"}` |
| `GET`  | `/rooms/{name}/messages` | Historique des messages |

**WebSocket** : `ws://localhost:8000/ws/{room_name}?user_name={user_name}`  
Envoyer : `{"content": "Bonjour !"}` — Recevoir : `{"type": "message", "user": "alice", "content": "...", "timestamp": "..."}`

## Remettre à zéro la base de données

```bash
rm whatsapp.db
```

## Structure du projet

```
eval-whatsapp/
├── main.py            # Application FastAPI (routes REST + WebSocket)
├── static/
│   └── index.html     # Interface utilisateur (SPA)
└── README.md
```
