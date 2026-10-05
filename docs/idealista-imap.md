# Idealista por email (IMAP)

Idealista no se scrapea: se leen alertas del buzón.

## Variables en Render (Environment)
- `IMAP_ENABLED=true`
- `IMAP_HOST=imap.gmail.com`
- `IMAP_PORT=993`
- `IMAP_USER` — Gmail que recibe las alertas
- `IMAP_PASSWORD` — contraseña de aplicación (no la clave normal)
- `IMAP_FOLDER=INBOX` — o la carpeta/etiqueta elegida

No pegues estas claves en el chat.

## Comprobar
1. Abre `https://TU-SERVICIO.onrender.com/healthz`
2. Debe verse `"idealista_active": true` (y `enabled`/`configured` true).
3. En Idealista, crea alertas de **casas/chalets** hacia ese Gmail.
4. Pulsa **Actualizar** en el listado. Si hay correos nuevos con `/inmueble/…`, aparecen en **Por revisar** con portal Idealista.

## Notas
- Con `IMAP_ENABLED=true`, Actualizar incluye Idealista automáticamente.
- Los anuncios de email pueden llegar con datos incompletos; se aceptan para revisión salvo pisos claros o precio fuera de rango.
