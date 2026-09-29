# Frontend: Vite + React

A minimal starter. It has one Home page that checks the backend (`/health`, `/ai/providers`)
and a 404 page, laid out in the folder structure the project follows. See
[../design.md](../design.md) §5 for the conventions.

## Setup

```bash
cd frontend
cp .env.example .env     # set VITE_API_BASE_URL if your backend isn't on :8000
npm install
npm run dev              # http://localhost:5173
```

## Environment

| Variable              | Default                        | Notes                                      |
| --------------------- | ------------------------------ | ------------------------------------------ |
| `VITE_API_BASE_URL`   | `http://localhost:8000/api/v1` | Backend URL including the API prefix       |
| `VITE_API_TIMEOUT_MS` | `30000`                        | Default request timeout (AI calls get 90s) |

`VITE_*` values end up in the JS bundle, so never put secrets in them. A shell variable overrides `.env`:
`VITE_API_BASE_URL=https://api.example.com/api/v1 npm run dev`.

## Scripts

`npm run dev` · `npm run build` · `npm run preview` · `npm test` · `npm run test:watch` · `npm run lint`

## Folder structure

```
src/
  api/api.js            the only place that does HTTP (base URL, auth token, errors, endpoints)
  hooks/                useAsync, useAuth
  context/              AuthProvider, AppProviders
  components/ui/        reusable primitives: Button, Card, Spinner (one CSS module each)
  components/layout/    AppLayout (header + nav + <Outlet/>)
  pages/<Name>/         one folder per page: Home, NotFound
  styles/global.css     design tokens (light + dark) and reset
  utils/                cn()
  test/                 Vitest setup + render helpers
```

## Adding a page

1. `src/api/api.js`: add `export const ordersApi = { list: (params, o) => api.get('/orders', { ...o, params }) }`
2. `src/hooks/useOrders.js`: `useAsync(({ signal }) => ordersApi.list({}, { signal }), [])`
3. `src/pages/Orders/OrdersPage.jsx` + `OrdersPage.module.css`
4. Add a `<Route path="orders" element={<OrdersPage />} />` in `App.jsx` and a link in `AppLayout.jsx`
