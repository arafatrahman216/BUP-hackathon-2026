# Frontend: Vite + React

A small dashboard that uses every feature of the FastAPI backend: health, items CRUD, the AI provider chain, and Supabase Storage files. It's written in plain JavaScript and styled with CSS Modules and design tokens. There's no UI library.

## Setup

```bash
cd frontend
cp .env.example .env     # set VITE_API_BASE_URL if your backend isn't on :8000
npm install
npm run dev              # http://localhost:5173
```

Start the backend first. Its CORS settings already allow `http://localhost:5173` and `:3000`.

## Environment

| Variable              | Default                        | Notes                                                    |
| --------------------- | ------------------------------ | -------------------------------------------------------- |
| `VITE_API_BASE_URL`   | `http://localhost:8000/api/v1` | Backend URL including the API prefix                    |
| `VITE_API_TIMEOUT_MS` | `30000`                        | Default request timeout. AI calls always get at least 90s |

Vite embeds `VITE_*` values in the bundle when it builds, so never put secrets in them. A shell variable overrides `.env`, which makes switching backends a one-liner:

```bash
VITE_API_BASE_URL=https://api.example.com/api/v1 npm run dev
```

## Scripts

| Script               | What it does                                     |
| -------------------- | ------------------------------------------------ |
| `npm run dev`        | Dev server with HMR                              |
| `npm run build`      | Production build into `dist/`                    |
| `npm run preview`    | Serve the production build                       |
| `npm test`           | Vitest + Testing Library (jsdom), single run     |
| `npm run test:watch` | Tests in watch mode                              |
| `npm run lint`       | oxlint (React hooks rules included)              |

Docker: `docker build -t frontend . && docker run -p 5173:5173 -e VITE_API_BASE_URL=http://localhost:8000/api/v1 frontend`. On a bind mount without file events (macOS/Windows), add `-e CHOKIDAR_USEPOLLING=true`.

## Folder structure

```
src/
  api/api.js            the only place that does HTTP (base URL, auth, errors, endpoints)
  hooks/                useAsync, useMutation, useDebounce, useItems, useFiles, useToast, useAuth, useTheme, useCopyToClipboard
  context/              AuthProvider + ToastProvider (and their context objects), AppProviders
  components/
    ui/                 reusable building blocks: Button, Input, Select, Modal, Table, Toast... (one CSS module each)
    layout/             AppLayout, Sidebar, Header, PageHeader, navigation.js
  pages/<Page>/         one folder per page. Page-only components live next to the page
  styles/global.css     design tokens (light + dark), reset, keyframes
  utils/                cn(), formatters, error-message helpers
  test/                 Vitest setup + render helpers
```

## How the API layer works

- `request(path, options)` wraps `fetch`. It JSON-encodes plain objects and sends `FormData` as-is. It skips empty query params and times out through an `AbortController`. It also accepts a caller `signal`.
- If a token is stored (`setToken`), every request gets `Authorization: Bearer <token>`. On a **401** the token is cleared and `auth:unauthorized` is fired on `window`. `AuthProvider` listens for that event and updates its state.
- Every failure throws an `ApiError` with `status`, `code`, `message`, `details`, `requestId` and `retryAfter`. This includes network errors (`NETWORK_ERROR`) and timeouts (`TIMEOUT`). `error.fieldErrors` turns backend 422/409 details into `{name: "..."}` so forms can show messages under the right field.
- Endpoints are grouped by resource: `healthApi`, `itemsApi`, `aiApi`, `filesApi`.

## Recipes

**Add an endpoint.** Add a function to the right group in `src/api/api.js`, or add a new group:

```js
export const notesApi = {
  list: (params, options) => api.get('/notes', { ...options, params }),
  create: (data, options) => api.post('/notes', data, options),
}
```

**Read data in a component.**

```js
const { data, loading, error, refetch } = useAsync(({ signal }) => notesApi.list({ page }, { signal }), [page])
```

**Write data** (loading state and toasts come built in, and `mutate` never throws):

```js
const create = useMutation(notesApi.create, { successMessage: 'Note saved', onSuccess: refetch })
const { error } = await create.mutate({ title })
if (error) setErrors(error.fieldErrors)
```

**Add a page.**

1. Create `src/pages/Notes/NotesPage.jsx` with a default export, plus `NotesPage.module.css`.
2. Register it in `src/App.jsx`: `const NotesPage = lazy(() => import('./pages/Notes/NotesPage'))` and `<Route path="notes" element={<NotesPage />} />`.
3. Add it to the sidebar in `src/components/layout/navigation.js`.

`pages/Items` is the reference example to copy. It uses a hook for data and mutations (`hooks/useItems.js`), with the table and form modal as separate components next to the page.

## Design system

Colors, spacing, radius, shadows and type are CSS variables in `src/styles/global.css`. Dark mode follows the OS. The header toggle overrides it with `html[data-theme]`. To re-brand the app, change `--color-accent*`.
