# Project guide for coding agents

@design.md
@features.md

## Rules
- Follow the structure and conventions in design.md. For new backend resources, copy the Items resource layer by layer.
- Build what features.md lists as `todo`. Mark features `done` and fill in their Notes when finished.
- **Record every new design decision** (library, pattern, data model, UI convention) in design.md's decision log, and update the folder tables if you add folders.
- New env vars: declare them in `backend/app/core/config.py` and document them in `backend/.env.example` (frontend: `frontend/.env.example`).
- Never commit `.env` files or expose `SUPABASE_SERVICE_ROLE_KEY` to the frontend.
- Run `cd backend && .venv/bin/pytest` (and the frontend tests) before calling a task done.
