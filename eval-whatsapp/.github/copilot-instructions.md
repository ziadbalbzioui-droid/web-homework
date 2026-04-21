# Project Guidelines

## Architecture
This is a WhatsApp-like web app built with FastAPI (backend), WebSockets (real-time messaging), SQLite (database), and React + Tailwind (frontend). Key components include users, rooms (channels), and messages. Users and rooms are pre-created via CLI; no authentication initially. Reference 00-README-eval.md for detailed requirements.

## Build and Test
- Start server: `fastapi dev` (auto-reloads on changes)
- Reset DB: `rm *.db`
- Test API: Use httpie, e.g., `http POST http://localhost:8000/users name=alice`

## Conventions
- Users and rooms created from command line only (no UI for creation initially)
- WebSocket for messaging; REST for setup
- SQLite DB files stored at project root
- Follow class notes app patterns for WebSocket implementation