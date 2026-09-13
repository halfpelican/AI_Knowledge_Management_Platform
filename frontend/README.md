# Organisational Knowledge Platform — frontend

- Install: `npm install` (Node 24; versions are pinned exactly, `.npmrc` keeps new additions pinned).
- Dev server: `npm run dev`, then open http://127.0.0.1:5173/ (the component sheet is at `/components`).
- Build: `npm run build` writes `dist/`; `npm run lint` runs the template's Oxlint rules.
- API: requests go to `/api` on the same origin (D-21). In development `vite.config.js` proxies `/api` to the Django server at http://127.0.0.1:8000, so run `python manage.py runserver` alongside `npm run dev`. `VITE_API_BASE_URL` in `.env` (see `.env.example`) overrides the path only if the API is served elsewhere.
- Auth: the session cookie is HttpOnly and never handled by the front end; unsafe requests send `X-CSRFToken` from the `csrftoken` cookie. Screens: `/register`, `/login`, `/admin/roles` (Administrator only), `/403` (Access Denied, where a guarded route sends an unauthorised navigation attempt, FR-06).
- Password rules live in `src/utils/password.js` and nowhere else. They mirror `apps/accounts/validators.py` `ComplexityValidator`: minimum 8 characters, 1 uppercase, 1 number and 1 special character from ASCII punctuation, whitespace excluded. Change both together or the registration form will enable its submit button for a password the server rejects.
- `src/api/client.js` is the only module allowed to call `fetch`; components and hooks import it and never fetch directly.

---

# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.
