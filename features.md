# Features

This is the build list for the project. The human writes features here; the coding agent
reads this file (together with [design.md](design.md)) and implements them.

## How to use this file

**Human:** add a feature using the template below. Keep it short: what the user can do,
the rules that matter, and what "done" looks like. Leave blank anything you don't know yet.

**Coding agent:**
1. Read [design.md](design.md) first and follow its structure and conventions.
2. Build features whose status is `todo`, from top to bottom, unless told otherwise.
3. Backend: copy the Items resource (model → schema → repository → service → controller →
   register router → dependency). Frontend: add a page folder under `src/pages/` and the
   endpoint functions in `src/api/api.js`.
4. Add or update tests for what you build.
5. When a feature is done, set its status to `done` and list what you added under **Notes**
   (endpoints, pages, tables).
6. If you make a new design decision (library, pattern, data model), record it in the
   decision log in design.md.
7. If something here is unclear or contradicts design.md, ask. Don't guess.

Status values: `todo` · `in-progress` · `done` · `blocked`

---

## Template (copy this block)

```markdown
### F<n>: <Feature name>
- **Status:** todo
- **Priority:** high | medium | low
- **User story:** As a <user>, I want to <action> so that <benefit>.
- **Details / rules:**
  - ...
- **Data:** <new tables/fields, or "none">
- **API:** <endpoints you expect, or "agent decides">
- **UI:** <pages/components, or "agent decides">
- **Uses AI?:** no | yes: <what the model does>
- **Acceptance criteria:**
  - [ ] ...
- **Notes:** <filled in by the agent when done>
```

---

## Features

### F0: Demo resource (Items)
- **Status:** done
- **Priority:** high
- **User story:** As a developer, I want a complete example resource so that I can copy it for new features.
- **Details / rules:** Items CRUD with pagination and search, unique names, and AI-generated descriptions.
- **Data:** `items` table
- **API:** `/api/v1/items` (GET list, GET one, POST, PATCH, DELETE, POST `/{id}/generate-description`)
- **UI:** Items page
- **Uses AI?:** yes: writes a product description
- **Acceptance criteria:**
  - [x] CRUD works end to end
  - [x] Errors use the standard error shape
- **Notes:** Reference implementation. Don't delete it until you have your own features built.

<!-- Add your features below this line -->
