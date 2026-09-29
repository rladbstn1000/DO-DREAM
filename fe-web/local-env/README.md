# Phase-1 environment isolation

`npm run dev:local` and `npm run build -- --mode phase1` select this directory as
Vite's environment directory. It deliberately contains no environment files, so
existing `fe-web/.env*` deployment settings are never loaded for local validation.
The default browser API paths are `/api` and `/ai` on the same origin.

The local container uses `nginx.local.conf` to route these paths to Spring and
FastAPI. The development server forwards them to loopback ports 18082 and 18000.
Its frontend port is 5173 and `strictPort` prevents silently switching ports.
