# Project guide for coding agents

@design.md
@features.md

## Rules
- Follow the structure and conventions in design.md (new features: §3.6). The project is backend-only; don't build a frontend.
- Build what features.md lists as `todo`. Mark features `done` and fill in their Notes when finished.
- **Record every new design decision** (library, pattern, data model, UI convention) in design.md's decision log, and update the folder tables if you add folders.
- New env vars: declare them in `backend/app/core/config.py` and document them in `backend/.env.example`.
- Never commit `.env` files or expose `SUPABASE_SERVICE_ROLE_KEY` to the frontend.
- Run `cd backend && .venv/bin/pytest` before calling a task done.
