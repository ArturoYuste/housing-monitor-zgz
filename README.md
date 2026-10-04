# Housing Monitor

Panel web ligero para filtrar y gestionar casas en pueblos de Zaragoza (fuera de la ciudad). Primer slice: dashboard por estados, criterios editables y escaneo demo con motor de filtros.

## Perfil de búsqueda actual

- Provincia: Zaragoza, fuera de capital
- Pueblos configurables en `/settings`
- Máx. 180.000 €
- Casa ≥ 100 m² con jardín/terreno
- Reforma integral aceptada

## Stack

- Python 3.12+
- FastAPI + Jinja2 + HTMX + Tailwind (CDN)
- Persistencia JSON local en `data/`
- Siguiente fase de datos/hosting: Supabase + Render (sin Git sync)

## Arranque local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 43127 --reload
```

Abre [http://127.0.0.1:43127](http://127.0.0.1:43127).

## Qué incluye este slice

- Dashboard: Pendientes, Favoritos, Contactados, Descartados
- Cambio de estado y notas vía HTMX
- Criterios (pueblos, precio, jardín/terreno, etc.) → `data/config.json`
- Escaneo demo sobre `data/demo_catalog.json`

## Próximos pasos

- Scrapers reales (Fotocasa + Idealista por alertas email)
- Persistencia en Supabase
- Despliegue gratis en Render

## Email / IMAP (Idealista)

1. Copy `.env.example` to `.env` and fill IMAP settings.
2. Set `IMAP_ENABLED=true` when ready.
3. Create Idealista alerts to that inbox.
4. Until then, "Ejecutar escaneo" uses the demo catalog and still runs the same filters.

Other portals (Fotocasa, Habitaclia, Pisos.com) are wired in the runner and will be filled next.

## Portales activos ahora

- **Fotocasa**, **Habitaclia**, **Pisos.com**: escaneo HTTP real por pueblos del config.
- **Idealista**: pendiente de email/IMAP.
- El botón "Ejecutar escaneo (portales)" consulta los portales activos y aplica filtros.

## Opcional

```bash
# background scan every 30 minutes
export SCAN_INTERVAL_MINUTES=30

# Supabase sync (tables: properties, app_config with jsonb `data`)
export SUPABASE_URL=...
export SUPABASE_SERVICE_KEY=...
```

## Despliegue (Render + Supabase)

1. Ejecuta `supabase/schema.sql` en tu proyecto Supabase.
2. En Render, crea un Web Service / Blueprint con este repo (`render.yaml`).
3. Configura `SUPABASE_URL` y `SUPABASE_SERVICE_KEY`.
4. Abre la URL pública de Render (`/healthz` para healthcheck).

Guía detallada en el Context del proyecto: `docs/deploy-render-supabase.md`.
