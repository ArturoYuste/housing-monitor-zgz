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
