# BUP-hackathon-2026

Hackathon template: FastAPI backend (local Postgres container, Supabase Storage, multi-provider AI with fallback)
and a Vite React frontend, all started with one command.

## Quick start

```bash
cp backend/.env.example backend/.env      # AI keys; SUPABASE_* only needed for Storage
cp frontend/.env.example frontend/.env
docker compose up --build
```

- Frontend: http://localhost:5173
- API docs: http://localhost:8001/docs
- Postgres: localhost:5432 (user/password/db `fuel`)
- The simulator runs separately on :8000 (`cd simulator && docker compose up -d`)

## Docs
- [design.md](design.md): architecture, folder guide, conventions, decision log
- [features.md](features.md): the feature list the coding agent builds from
