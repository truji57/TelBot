# Changelog — TelBot

## v0.22 — 2026-07-22
- Reorganización del proyecto en carpetas bot/ y data/

## v0.21 — 2026-07-17
- TP_INDEX configurable para elegir TP1, TP2 o TP3

## v0.20 — 2026-07-17
- Quitado StratiX del banner

## v0.19 — 2026-07-17
- Run_bot solo avisa de actualización, no actualiza automáticamente

## v0.18 — 2026-07-17
- Banner con StratiX

## v0.17 — 2026-07-17
- Aviso de actualización en run_bot al arrancar, sin actualizar automáticamente

## v0.16 — 2026-07-17
- Eliminado update_now.bat redundante

## v0.15 — 2026-07-17
- Actualización manual sin caché, run_bot solo arranca sin actualizar

## v0.14 — 2026-07-02
- Add: CHANGELOG.md con historial completo de versiones
- Add: opencode.json con comando `commit` que auto‑bumpea versión, actualiza changelog y hace push

## v0.13 — 2026-06-09
- Fix: doble apertura del navegador al lanzar `config_panel.bat`

## v0.12 — 2026-06-09
- Add: `update_now.bat` para forzar comprobación y descarga de actualizaciones sin esperar la caché de 24h
- Fix: puerto del panel por defecto cambiado a `8765`, acepta argumento CLI (`python config_panel.py 9090`)

## v0.11 — 2026-06-09
- Add: `config_panel.py` — panel web local para editar `.env` desde el navegador
- Organizado por secciones (GitHub, Telegram, Canales, MT5, Riesgo, Modo, Polling)
- Add: `config_panel.bat` para lanzarlo con doble clic

## v0.10 — 2026-06-09
- Add: `ORDER_RETRY_COUNT` y `ORDER_RETRY_DELAY` en `.env` — reintentos al enviar órdenes a MT5
- Solo reintenta en errores transitorios (requote, timeout, precio inválido, precio cambiado, sin conexión)
- Parámetros: retcode 10006, 10012, 10015, 10020, 10031

## v0.09 — 2026-06-05
- Add: fallback de descarga ZIP vía API de GitHub en `updater.py`
- Cuando `git fetch` falla (ej: DNS no resuelve `github.com`), descarga el repo como ZIP y extrae los archivos
- No sobreescribe `.env`, `logs/`, `processed_messages.csv`, etc.

## v0.08 — 2026-06-04
- Refactor `RANDOM_OFFSET_TICKS`: ahora el offset se aplica siempre **hacia el precio de mercado**
- Si entry < precio actual → suma ticks (acerca al mercado)
- Si entry > precio actual → resta ticks (acerca al mercado)
- Así las órdenes tienen más probabilidad de ejecutarse

## v0.07 — 2026-06-01
- Add: `RANDOM_OFFSET_TICKS` en `.env` — offset aleatorio en entry/SL/TP para evitar detección de group trading
- Aplica un desplazamiento aleatorio (±N ticks) a todos los precios de la operación

## v0.06 — 2026-06-01
- Add: `ORDER_COMMENT` en `.env` — comentario personalizado en las órdenes de MT5 (vacío = sin comentario)
- Fix: `DEFAULT_MAGIC` ahora acepta vacío (pasa a `0`, sin magic number)

## v0.05 — 2026-06-01
- Fix: ciclo de reconexión infinita — el polling ya no reconecta por su cuenta, solo el bucle principal
- Fix: `_translate_symbol` ahora busca en el mapa con case‑insensitive
- Add: auto‑detección de símbolo en MT5 si no está en `symbols_map.yaml` (busca por prefijo)
- Fix: traducción de símbolo aplicada antes de `calcular_lotes()` para evitar `RuntimeError`

## v0.04 — 2026-05-27
- Add: sistema de comandos (`/help`, `/ping`, `/status`, `/positions`, `/orders`, `/closeall`, `/close`, `/deleteall`, `/be`, `/setsl`, `/settp`)
- Add: funciones MT5 de control (cerrar posiciones, eliminar órdenes, breakeven, modificar SL/TP)
- Add: handler de eventos para `CONTROL_CHAT_ID`
- Fix: `CONTROL_CHAT_ID` ahora es opcional (no bloquea si está vacío o incorrecto)
- Opt: updater usa API HTTP de GitHub en lugar de `git ls-remote` (mucho más rápido, 0.76s vs 37s)
- Opt: caché de 24h en el updater

## v0.03 — 2026-05-26
- Fix: `.env.example` — `FORWARD_CHAT_ID` en lugar de `NOTIFY_CHAT_ID`
- Fix: excluir scripts de instalación del repo

## v0.02 — 2026-05-26
- Add: número de versión en el banner
- Fix: `.env.example` con `GITHUB_REPO` por defecto
- Fix: excluir archivos personales del repo (NO NECESARIO 2, Para mandar, CLAUDE.md, PENDIENTES.md)

## v0.01 — 2026-05-26
- Commit inicial
- Bot escucha canal de Telegram y reenvía señales a MT5
- Parser local de señales con regex (formato estructurado, libre y resumen)
- `risk_manager.py` — cálculo de lotes según porcentaje de riesgo
- `mt5_connector.py` — conexión a MT5, envío de órdenes market/limit/stop
- `updater.py` — auto‑actualización desde GitHub
- `telegram_listener.py` — entry point con reconexión automática y polling de mensajes
- `symbols_map.yaml` — mapeo de símbolos por broker
- Modo DRY_RUN para pruebas sin ejecutar órdenes reales
- Confirmación de trades vía botones Sí/No en Telegram
