# CLAUDE.md — Trading Bot: Telegram → MetaTrader 5

## Behavior Rules

- Editar archivos directamente, sin mostrar bloques de código como alternativa.
- No resumir lo cambiado tras editar a menos que se pida.
- Comunicarse exclusivamente en español castellano.
- Revisar PENDIENTES.md antes de cada sesión para conocer bugs y prioridades.

## 🎯 Objetivo del proyecto

Construir un bot de trading automatizado que:
1. **Escucha en tiempo real** un canal de Telegram de señales de trading
2. **Interpreta** los mensajes usando un algoritmo propio basado en expresiones regulares (**local_signal_parser**)
3. **Ejecuta automáticamente** las operaciones en MetaTrader 5 vía Python
4. **Notifica** al usuario en su Telegram personal el resultado de cada operación

El usuario **no necesita estar delante del PC**. El bot corre en segundo plano (o en un VPS) y actúa de forma autónoma.

---

## 🏗️ Arquitectura del sistema

```
Canal Telegram (señales)
        ↓  [Telethon — escucha en tiempo real + polling cada 15s]
telegram_listener.py  →  local_signal_parser.py (parser local con regex)
                     →  risk_manager.py (cálculo de lotes)
                                ↓
                        mt5_connector.py (MetaTrader 5)
                                ↓
                        Reenvío a FORWARD_CHAT_ID (Telegram)
```

---

## 📁 Estructura de archivos del proyecto

```
TelBot/
├── CLAUDE.md                  # Este archivo
├── .env                       # Variables de entorno (NO subir a git)
├── .env.example               # Plantilla del .env
├── .gitignore
├── requirements.txt           # Dependencias Python
├── run_bot.bat                # Script de arranque en Windows
├── install_requirements.bat   # Instalar dependencias
├── telegram_listener.py       # Entry point: escucha + orquesta todo
├── local_signal_parser.py     # Interpreta señales con regex local
├── mt5_connector.py           # Conexión y envío de órdenes a MT5
├── risk_manager.py            # Cálculo de lotes según riesgo
├── config.py                  # Carga de .env y configuración
├── symbols_map.yaml           # Mapeo de símbolos por broker
├── MetaTrader5.pyi            # Stub para type hints
├── send_order_demo.py         # Demo para probar órdenes
├── test_all_parsers.py        # Tests del parser
├── test_polling.py            # Tests del polling
├── PENDIENTES.md              # Bugs y tareas pendientes
├── processed_messages.csv     # Registro de mensajes procesados
├── last_processed_id.txt      # Último ID procesado
├── logs/
│   └── trading_bot.log        # Log persistente
├── NO-NECESARIO/              # Archivos antiguos (no tocar)
│   ├── venv/
│   ├── SETUP.md
│   └── ...
└── Nueva carpeta/             # Backups (no tocar)
```

---

## ⚙️ Stack tecnológico

| Componente | Librería/Herramienta | Versión mínima |
|---|---|---|
| Lenguaje | Python | 3.10+ |
| Leer Telegram | Telethon | 1.36+ |
| Interpretar señales | **Regex local** (sin API externa) | — |
| Ejecutar trades | MetaTrader5 (oficial) | 5.0.45+ |
| Enviar notificaciones | python-telegram-bot | 21+ |
| Variables de entorno | python-dotenv | 1.0+ |
| Logs | logging (stdlib) | — |

> ⚠️ **La librería MetaTrader5 solo funciona en Windows.** Si se desarrolla en Mac/Linux, usar un VPS Windows o una VM.

---

## 🔑 Variables de entorno necesarias (.env)

```env
# === TELEGRAM API (obtener en https://my.telegram.org) ===
TELEGRAM_API_ID=tu_api_id
TELEGRAM_API_HASH=tu_api_hash
TELEGRAM_PHONE=+34612345678

# === CANAL DE SEÑALES ===
# Puede ser el @username del canal o su ID numérico negativo
SIGNAL_CHANNEL=@nombre_del_canal

# === BOT DE NOTIFICACIONES (crear en @BotFather) ===
NOTIFY_BOT_TOKEN=123456:ABC-token-del-bot
NOTIFY_CHAT_ID=tu_chat_id_personal

# === CANAL DE SEÑALES (opcional, para reenvío) ===
FORWARD_CHAT_ID=otro_chat_id  # Opcional: chat donde se reenvían mensajes no detectados

# === GESTIÓN DE CONFIRMACIÓN ===
CONFIRM_TRADES=false           # true=espera confirmación, false=ejecuta directo
DRY_RUN=false                  # true=simula sin ejecutar, false=ejecuta real

# === METATRADER 5 ===
MT5_LOGIN=12345678
MT5_PASSWORD=tu_password
MT5_SERVER=NombreBroker-Real   # o NombreBroker-Demo para pruebas

# Configuración del polling de mensajes perdidos
POLLING_INTERVAL=15   # Segundos entre cada revisión del canal
MESSAGE_LIMIT=20      # Máximo de mensajes a buscar en cada ping

```
---

## 🧠 Lógica del local_signal_parser.py

Este módulo interpreta los mensajes del canal de señales **sin usar API externa**, solo con expresiones regulares (regex).

### Formatos soportados

**1️⃣ Formato estructurado (con etiquetas):**
```
🟢 BUY XAUUSD
  Entry: 4708.24
  TP1: 4724.03
  TP2: 4739.60
  SL: 4695.58
```

**2️⃣ Formato libre (rango de precios + TP en líneas separadas):**
```
SELL XAUUSD 4696-4700

SL 4704

TP 4693
TP 4691
TP 4685
```

**3️⃣ Formato resumen (para escalonar bots):**
```
📋 RESUMEN DE OPERACIÓN
  Señal: SELL BTCUSD
  Tipo:  STOP @ 78300.00000
  SL:    78482.00000
  TP1=78124.00000 | TP2=77943.00000 | TP3=77766.00000
  Lots:  0.40
```

### Reglas de extracción

- **Acción**: `BUY` o `SELL` (primera línea)
- **Símbolo**: `XAUUSD`, `EURUSD`, etc.
- **Entry**:
  - En formato estructurado: `Entry: <precio>`
  - En formato libre: si hay rango `4696-4700`, para `SELL` toma el **menor** (4696), para `BUY` toma el **mayor** (4700)
- **SL**: `SL <precio>` o `SL: <precio>`
- **TP**: todos los valores `TP` encontrados (hasta 3), en orden de aparición

### Ejemplo de mensaje no detectado
Si el mensaje no coincide con ningún formato, se reenvía al chat de destino con el prefijo:

```
⚠️ *No detectado como señal*

<texto original>

---
```

---

## 📊 Lógica del risk_manager.py

```python
# Fórmula de cálculo de lotes (para XAUUSD, contract_size=100)
balance = mt5.account_info().balance
risk_amount = balance * (RISK_PERCENT / 100)
sl_dist = abs(entry - sl)
tick_size = symbol_info.trade_tick_size  # 0.01 para XAUUSD
tick_value = contract_size * tick_size   # 100 * 0.01 = 1.0 USD por tick
sl_ticks = sl_dist / tick_size
loss_per_lot = sl_ticks * tick_value
lot_size = risk_amount / loss_per_lot
lot_size = min(max(lot_size, MIN_LOT_SIZE), MAX_LOT_SIZE)
```

---

## 🔄 Flujo completo de una operación con DRY_RUN=false

```
1. Telethon recibe mensaje nuevo en el canal
2. Se llama a local_signal_parser.py con el texto
3. Parser local devuelve JSON con la señal parseada
4. Si is_signal = false → se ignora (log de info)
5. Si is_signal = true:
   a. risk_manager calcula el tamaño de lote
   b. mt5_connector valida que el símbolo existe en MT5
   c. mt5_connector envía la orden (market order o pending)
   d. MT5 confirma la ejecución
   e. notifier envía mensaje a Telegram personal del usuario
   f. logger registra todo en el archivo de log
6. Si hay error en cualquier paso → notifier avisa del error
```

---

## 🛡️ Gestión de errores

- **MT5 no conectado**: el bot lo detecta al arrancar y avisa. No ejecuta operaciones sin conexión confirmada.
- **Señal ambigua**: si el parser local no puede extraer los datos, marca `is_signal: false` y notifica al usuario para revisión manual.
- **Símbolo no encontrado en MT5**: algunos brokers usan sufijos (EURUSD.m, EURUSDpro). El bot debe intentar variantes automáticamente.
- **Error de ejecución en MT5**: capturar el código de error de MT5 y notificar con descripción legible.
- **Desconexión de Telegram**: el bot detecta la caída y reconecta automáticamente con backoff exponencial (5s → 5min máx). El polling periódico tiene reconexión propia independiente del bucle principal.

## 🚀 Modo Dry‑Run (solo reenvío)

Cuando `DRY_RUN=true` el bot **no intenta conectar a MetaTrader 5**.  
Simplemente reenvía el mensaje tal cual al canal secundario, sin procesar riesgos ni ejecutar órdenes.  
Este modo es útil para:

- Depurar la cadena de reenvío sin tocar MT5.
- Permitir que otros sistemas consuman las señales directamente.
- Mantener el bot activo sin riesgos de operación real.

En este modo el bot no llama a `mt5.initialize`, `mt5.login` ni a `mt5.account_info()`.  
El cálculo de riesgo se basa en un balance ficticio (`1`) solo para pasar el flujo de código, pero **no se ejecuta ninguna orden**.

---

## 🧪 Modo de prueba (DEMO)

Antes de conectar a cuenta real, el bot debe funcionar en modo demo:
- Usar cuenta demo del broker en MT5
- Añadir variable `DRY_RUN=true` en .env para simular sin ejecutar nada
- En modo DRY_RUN: parsea y loguea la señal pero NO manda orden a MT5

---

## 📋 Comandos de desarrollo

```bash
# Instalar dependencias
pip install -r requirements.txt

# Arrancar el bot (primer uso — pedirá código de verificación de Telegram)
run_bot.bat

# O directamente con python
python telegram_listener.py

# Ver logs en tiempo real en Windows
Get-Content logs\trading_bot.log -Tail 20 -Wait
```
