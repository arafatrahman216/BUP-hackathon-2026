# Features

This is the build list for the project. The human writes features here; the coding agent
reads this file (together with [design.md](design.md)) and implements them.

## How to use this file

**Human:** add a feature using the template below. Keep it short: what the user can do,
the rules that matter, and what "done" looks like. Leave blank anything you don't know yet.

**Coding agent:**
1. Read [design.md](design.md) first and follow its structure and conventions.
2. Build features whose status is `todo`, from top to bottom, unless told otherwise.
3. Follow design.md §3.6 (model → schema → repository → service → dependency →
   controller → register router). This project is backend-only; don't build frontend pages.
4. Add or update tests for what you build.
5. When a feature is done, set its status to `done` and list what you added under **Notes**
   (endpoints, tables).
6. If you make a new design decision (library, pattern, data model), record it in the
   decision log in design.md.
7. If something here is unclear or contradicts design.md, ask. Don't guess.

Status values: `todo` · `in-progress` · `done` · `blocked`

---



---

## Features

<!-- Add your features below this line -->
