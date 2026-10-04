# Housing Monitor

Panel web ligero para filtrar y gestionar anuncios inmobiliarios. Primer slice: dashboard por estados, criterios editables y escaneo demo con motor de filtros (sin scrapers reales todavía).

## Stack

- Python 3.12+
- FastAPI + Jinja2 + HTMX + Tailwind (CDN)
- Persistencia JSON en `data/`

## Arranque local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 43127 --reload
```

Abre [http://127.0.0.1:43127](http://127.0.0.1:43127).

## Qué incluye este slice

- Dashboard con pestañas: Pendientes, Favoritos, Contactados, Descartados
- Cambio de estado y notas vía HTMX
- Pantalla de criterios que escribe `data/config.json`
- Escaneo demo sobre `data/demo_catalog.json` usando `scraper/filter_engine.py`

## Estructura

```text
app/                 # FastAPI, templates, static
scraper/             # Filter engine + demo runner (+ placeholders de portales)
data/                # config.json, properties.json, demo_catalog.json
requirements.txt
```

## Próximos pasos

- Scrapers reales (Fotocasa, Idealista, etc.)
- Persistencia remota en GitHub / Gist
- Despliegue gratuito (Render o Koyeb)
