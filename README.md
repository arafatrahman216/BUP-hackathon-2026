# BUP-hackathon-2026

Hackathon template: FastAPI backend (Supabase DB + Storage, multi-provider AI with fallback)
and a Vite React frontend, all started with one command.

## Quick start

```bash
cp backend/.env.example backend/.env      # fill in the SUPABASE_* values and at least one AI key
cp frontend/.env.example frontend/.env
docker compose up --build
```

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs

## Docs
- [design.md](design.md): architecture, folder guide, conventions, decision log
- [features.md](features.md): the feature list the coding agent builds from
