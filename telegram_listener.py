"""telegram_listener.py
Escucha el canal de señales y reenvía mensajes al chat de destino.

DRY_RUN se omita la conexión a MT5, solo funciona Telegram.
"""
import os
import json
import csv
import logging
import asyncio
import time
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from telethon.tl.types import PeerChannel
from telethon.errors import RPCError
import MetaTrader5 as mt5

# Cargar configuración desde .env
from config import (
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    TELEGRAM_PHONE,
    SIGNAL_CHANNEL,
    FORWARD_CHAT_ID,
    MT5_LOGIN,
    MT5_PASSWORD,
    MT5_SERVER,
    MT5_TERMINAL_PATH,
    CONFIRM_TRADES,
    DRY_RUN,
)

# ---------------------------------------------------------------------------
# Preparar logging
# ---------------------------------------------------------------------------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/trading_bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

if not (TELEGRAM_API_ID and TELEGRAM_API_HASH):
    logger.error("Faltan TELEGRAM_API_ID o TELEGRAM_API_HASH en .env")
    raise SystemExit(1)

# Variables globales para entidades de canales
CHANNEL_SRC_ENTITY = None
CHANNEL_FORWARD_ENTITY = None

# Conjunto global para rastrear IDs de mensajes procesados y evitar duplicados
PROCESSED_MESSAGES = set()
# Variable global que mantiene el último ID de mensaje procesado
last_processed_id = 0
# Indica si el primer ciclo de polling ya se ejecutó (evita procesar historial al iniciar)
FIRST_POLL_DONE = False

# Variables globales para confirmación de trades y balance
PENDING_CONFIRMATIONS = {}
ACCOUNT_BALANCE = 0.0

# Variables de configuración del polling (leídas desde .env)
POLLING_INTERVAL = int(os.getenv("POLLING_INTERVAL", "15"))  # Segundos entre revisiones
MESSAGE_LIMIT = int(os.getenv("MESSAGE_LIMIT", "20"))         # Máximo de mensajes a revisar por ciclo

# Ruta para el archivo de persistencia del último ID procesado
LAST_PROCESSED_ID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_processed_id.txt")

# Ruta para el archivo CSV de mensajes procesados
MESSAGES_CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processed_messages.csv")

def load_last_processed_id():
    """Carga el último ID procesado desde el archivo persistente"""
    try:
        if os.path.exists(LAST_PROCESSED_ID_FILE):
            with open(LAST_PROCESSED_ID_FILE, "r") as f:
                return int(f.read().strip())
        return 0
    except:
        return 0

def save_last_processed_id(msg_id):
    """Guarda el último ID procesado en el archivo persistente"""
    with open(LAST_PROCESSED_ID_FILE, "w") as f:
        f.write(str(msg_id))

# ---------------------------------------------------------------------------
# Crear cliente Telethon (dentro de main para tener event loop)
# ---------------------------------------------------------------------------
client = None

# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
def _print_banner():
    banner = r"""
████████╗███████╗██╗     ██████╗  ██████╗ ████████╗
╚══██╔══╝██╔════╝██║     ██╔══██╗██╔═══██╗╚══██╔══╝
   ██║   █████╗  ██║     ██████╔╝██║   ██║   ██║
   ██║   ██╔══╝  ██║     ██╔══██╗██║   ██║   ██║
   ██║   ███████╗███████╗██████╔╝╚██████╔╝   ██║
   ╚═╝   ╚══════╝╚══════╝╚═════╝  ╚═════╝    ╚═╝
                      v0.02
    """
    print(banner)

async def main():
    global client, last_processed_id, CHANNEL_SRC_ENTITY, CHANNEL_FORWARD_ENTITY, ACCOUNT_BALANCE
    _print_banner()

    # Inicializar dentro del event loop (necesario en Python 3.12+)
    csv_lock = asyncio.Lock()
    client = TelegramClient("trading_bot", int(TELEGRAM_API_ID), TELEGRAM_API_HASH)

    async def save_message_to_csv(msg_id, text, timestamp=None):
        nonlocal csv_lock
        if timestamp is None:
            timestamp = datetime.now()
        file_exists = os.path.exists(MESSAGES_CSV_FILE)
        async with csv_lock:
            with open(MESSAGES_CSV_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(['message_id', 'text', 'timestamp'])
                writer.writerow([msg_id, text, timestamp.isoformat()])

    def get_all_processed_ids():
        message_ids = set()
        if not os.path.exists(MESSAGES_CSV_FILE):
            return message_ids
        with open(MESSAGES_CSV_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            try:
                next(reader)
            except:
                return message_ids
            for row in reader:
                if len(row) >= 1:
                    try:
                        message_ids.add(int(row[0]))
                    except:
                        continue
        return message_ids

    # Cargar último ID procesado desde archivo persistente al iniciar
    last_processed_id = load_last_processed_id()

    # Conectar cliente
    await client.start(phone=TELEGRAM_PHONE)
    logger.info("Cliente Telethon conectado")

    # ---------------------------------------------------------------
    # Resolver entidades de canales
    # ---------------------------------------------------------------
    try:
        # Canal de origen
        if SIGNAL_CHANNEL.lstrip("-").isdigit():
            src_id = int(SIGNAL_CHANNEL)
            CHANNEL_SRC_ENTITY = PeerChannel(src_id)
        else:
            CHANNEL_SRC_ENTITY = await client.get_input_entity(SIGNAL_CHANNEL)
        logger.info(f"Canal origen resuelto: {SIGNAL_CHANNEL}")
    except Exception as e:
        logger.error(f"No se pudo resolver el canal de origen {SIGNAL_CHANNEL}: {e}")
        raise SystemExit(1)

    try:
        # Canal de destino
        if FORWARD_CHAT_ID.lstrip("-").isdigit():
            dst_id = int(FORWARD_CHAT_ID)
            CHANNEL_FORWARD_ENTITY = PeerChannel(dst_id)
        else:
            CHANNEL_FORWARD_ENTITY = await client.get_input_entity(FORWARD_CHAT_ID)
        logger.info(f"Canal de destino resuelto: {FORWARD_CHAT_ID}")
    except Exception as e:
        logger.error(f"No se pudo resolver el canal de destino {FORWARD_CHAT_ID}: {e}")
        raise SystemExit(1)

    # ---------------------------------------------------------------
    # Conexön a MetaTrader 5 (solo si no es DRY_RUN)
    # ---------------------------------------------------------------
    if not DRY_RUN:
        try:
            try:
                if MT5_TERMINAL_PATH:
                    logger.info(f"Inicializando MT5 con ruta: {MT5_TERMINAL_PATH}")
                    initialized = mt5.initialize(MT5_TERMINAL_PATH)
                else:
                    logger.info("Inicializando MT5 con ruta por defecto (asumiendo que terminal esté en PATH)")
                    initialized = mt5.initialize()

                if not initialized:
                    logger.error("No se pudo iniciar MetaTrader5 (terminal no encontrada o error al preparar)")
                else:
                    # Intentar login con credenciales
                    if mt5.login(int(MT5_LOGIN), password=MT5_PASSWORD, server=MT5_SERVER):
                        logger.info("Conectado a MetaTrader5 exitosamente")
                        # Obtener y registrar información de la cuenta MT5
                        account_info = mt5.account_info()
                        if account_info:
                            ACCOUNT_BALANCE = account_info.balance
                            logger.info(
                                f"MT5 cuenta login={account_info.login}, server={account_info.server}, "
                                f"balance={account_info.balance}, equity={account_info.equity}, "
                                f"currency={account_info.currency}"
                            )
                            # Actualizar el balance global para logging
                            ACCOUNT_BALANCE = account_info.balance
                        else:
                            logger.error("No se pudo obtener información de la cuenta MT5")
                    else:
                        logger.error(f"Login a MetaTrader5 falló: {mt5.last_error()}")
            except Exception as e:
                logger.exception(f"Excepción al intentar conectar MT5: {e}")
        except Exception as e:
            logger.exception(f"Excepción al intentar conectar MT5: {e}")
    else:
        logger.info("MODO SECO activado: se omite la conexión a MT5")

    # ---------------------------------------------------------------
    # Función reutilizable para procesar mensajes (evento o fetch)
    # ---------------------------------------------------------------
    async def process_message(msg_or_event, is_fetched=False):
        """Procesa el mensaje recibido ya sea de un evento en tiempo real o mediante polling.
        is_fetched indica si el origen es una llamada a get_messages (True) o un evento (False).
        """
        try:
            # Si es un mensaje fetch, usamos .id y .message directamente; si es evento, usamos event.message
            if is_fetched:
                msg = msg_or_event
                chat_id = msg.chat_id
                text = msg.message
                msg_id = msg.id
            else:
                msg = msg_or_event.message
                chat_id = msg_or_event.chat_id
                text = msg.message
                msg_id = msg_or_event.id

            # Evitar procesar mensajes ya manejados
            if msg_id in PROCESSED_MESSAGES:
                return
            PROCESSED_MESSAGES.add(msg_id)

            logger.info(f"Mensaje recibido de chat_id: {chat_id} (esperado: {SIGNAL_CHANNEL})")
            logger.info(f"[MSJ] Mensaje ID:{msg_id} recibido en canal {SIGNAL_CHANNEL}: {text!r}")

            # Guardar mensaje en el archivo CSV
            await save_message_to_csv(msg_id, text)

            # Verificar que el chat_id coincide con el canal esperado
            if abs(chat_id) != int(SIGNAL_CHANNEL.lstrip('-')):
                logger.warning(f"Mensaje de chat incorrecto (ID: {chat_id}), ignorando")
                return

            logger.info(f"Mensaje recibido en canal {SIGNAL_CHANNEL}: {text!r}")

            if DRY_RUN:
                await client.send_message(CHANNEL_FORWARD_ENTITY, text, parse_mode='html')
                logger.info(f"Mensaje reenviado a {FORWARD_CHAT_ID} (modo seco)")
                return

            # 1️⃣ Parsear la señal
            from local_signal_parser import parse_signal
            parsed = parse_signal(text)
            if not parsed.get("is_signal", False):
                logger.info("El mensaje no es una señal válida → se ignora el parsing.")
                prefixed_text = f"""⚠️ *No detectado como señal*

{text}

---"""
                await client.send_message(CHANNEL_FORWARD_ENTITY, prefixed_text, parse_mode='html')
                logger.info(f"Mensaje con prefijo enviado a {FORWARD_CHAT_ID}")
                return

            # 2️⃣ Obtener parámetros y balance
            symbol = parsed.get("symbol")
            entry = parsed.get("entry")
            sl = parsed.get("sl")
            action = parsed.get("action")

            if not all([symbol, entry, sl, action]):
                logger.warning(f"Datos incompletos en señal: {parsed}")
                await client.send_message(CHANNEL_FORWARD_ENTITY, "Datos incompletos → señal ignorada")
                return

            if not DRY_RUN:
                account_info = mt5.account_info()
                if account_info is None:
                    logger.error("No se pudo obtener información de la cuenta MT5")
                    await client.send_message(CHANNEL_FORWARD_ENTITY, "Error: no se pudo obtener balance de MT5")
                    return
                current_balance = account_info.balance
            else:
                current_balance = 1

            # 3️⃣ Calcular riesgo y tipo de orden
            from risk_manager import calcular_lotes, determine_order_type, build_trade_summary
            lot = calcular_lotes(symbol, current_balance, entry, sl)
            order_type = determine_order_type(action, entry, symbol)
            summary_msg = build_trade_summary(parsed, lot, order_type)
            logger.info(f"Resumen de operación:\n{summary_msg}")

            # 4️⃣ Enviar resumen y manejar confirmación
            if CONFIRM_TRADES:
                buttons = [[Button.inline("[SUCCESS] Sí", b"confirm_yes"), Button.inline("❌ No", b"confirm_no")]]
                sent_msg = await client.send_message(CHANNEL_FORWARD_ENTITY, summary_msg, parse_mode='html', buttons=buttons)
                PENDING_CONFIRMATIONS[sent_msg.id] = (parsed, lot, order_type)
                logger.info(f"Mensaje de confirmación enviado (msg_id={sent_msg.id})")
            else:
                await client.send_message(CHANNEL_FORWARD_ENTITY, summary_msg, parse_mode='html')
                logger.info(f"Resumen enviado a {FORWARD_CHAT_ID}")

                if not DRY_RUN:
                    try:
                        from mt5_connector import send_order
                        parsed['lot_size'] = lot
                        result = send_order(parsed)
                        if result.get("success"):
                            logger.info(f"Orden ejecutada: {result}")
                            await client.send_message(CHANNEL_FORWARD_ENTITY, f"[SUCCESS] Orden ejecutada: {action} {symbol} @ {entry}")
                        else:
                            logger.error(f"Error al ejecutar orden: {result}")
                            await client.send_message(CHANNEL_FORWARD_ENTITY, f"❌ Error al ejecutar orden: {result.get('message')}")
                    except Exception as e:
                        logger.exception(f"Excepción al enviar orden: {e}")
                        await client.send_message(CHANNEL_FORWARD_ENTITY, f"❌ Error: {str(e)}")
                else:
                    logger.info("[MODO SECO] No se ejecutó la orden en MT5")
                    await client.send_message(CHANNEL_FORWARD_ENTITY, "⚠️ MODO SECO: operación simulada (no se ejecutó)")

        except RPCError as e:
            logger.error(f"Error al reenviar mensaje: {e}")
        except Exception as exc:
            logger.exception(f"Excepción inesperada en process_message: {exc}")

    # ---------------------------------------------------------------
    # Handler para mensajes del canal de origen
    # ---------------------------------------------------------------
    @client.on(events.NewMessage(chats=CHANNEL_SRC_ENTITY))
    async def handler(event):
        await process_message(event, is_fetched=False)

    # ----------------------------
    # Handler para botones de confirmación (Sí/No)
    # ----------------------------
    @client.on(events.CallbackQuery(data=b"confirm_yes"))
    async def handle_confirm_yes(event):
        msg_id = event.message.id
        if msg_id not in PENDING_CONFIRMATIONS:
            return
        parsed, lot, order_type = PENDING_CONFIRMATIONS[msg_id]
        del PENDING_CONFIRMATIONS[msg_id]

        action = parsed.get("action")
        symbol = parsed.get("symbol")
        entry = parsed.get("entry")

        if not DRY_RUN:
            try:
                from mt5_connector import send_order
                result = send_order(parsed)
                if result.get("success"):
                    logger.info(f"[SUCCESS] Confirmado y ejecutado: {action} {symbol} @ {entry}")
                    await client.send_message(event.chat_id, f"[SUCCESS] Orden ejecutada: {action} {symbol} @ {entry}")
                else:
                    logger.error(f"Error al ejecutar orden: {result}")
                    await client.send_message(event.chat_id, f"❌ Error al ejecutar orden: {result.get('message', 'Desconocido')}")
            except Exception as e:
                logger.exception(f"Error al enviar orden: {e}")
                await client.send_message(event.chat_id, f"❌ Error: {str(e)}")
        else:
            logger.info("[MODO SECO] Confirmación simulada")
            await client.send_message(event.chat_id, "⚠️ MODO SECO: confirmación simulada")

    @client.on(events.CallbackQuery(data=b"confirm_no"))
    async def handle_confirm_no(event):
        msg_id = event.message.id
        if msg_id not in PENDING_CONFIRMATIONS:
            return
        del PENDING_CONFIRMATIONS[msg_id]
        logger.info(f"❌ Confirmación denegada para msg_id {msg_id}")
        await client.send_message(event.chat_id, "⚠️ Operación cancelada por el usuario")

    # ---------------------------------------------------------------
    # Función de reconexión compartida
    # ---------------------------------------------------------------
    async def reconnect_client():
        """Reconecta el cliente Telethon y re-resuelve entidades."""
        global CHANNEL_SRC_ENTITY, CHANNEL_FORWARD_ENTITY
        try:
            if client.is_connected():
                await client.disconnect()
            await client.connect()
            await client.start(phone=TELEGRAM_PHONE)
            CHANNEL_SRC_ENTITY = await client.get_input_entity(SIGNAL_CHANNEL)
            CHANNEL_FORWARD_ENTITY = await client.get_input_entity(FORWARD_CHAT_ID)
            logger.info("[RECONNECTED] Reconexión exitosa")
            return True
        except Exception as e:
            logger.error(f"Falló la reconexión: {e}")
            return False

    # ---------------------------------------------------------------
    # Tarea de polling periódico para detectar mensajes perdidos
    # ---------------------------------------------------------------
    async def poll_missing_messages():
        """Cada POLLING_INTERVAL segundos revisa el canal en busca de mensajes no procesados.
        Incluye su propia lógica de reconexión por si el cliente se cae.
        """
        global last_processed_id, FIRST_POLL_DONE, CHANNEL_SRC_ENTITY
        interval = POLLING_INTERVAL
        limit = MESSAGE_LIMIT
        logger.info(f"Iniciando polling cada {interval}s, limit {limit}")
        last_all_clear_log = 0
        consecutive_failures = 0

        while True:
            try:
                logger.debug(f"[Polling] Ciclo cada {interval}s (limit={limit})")

                if not client.is_connected():
                    logger.warning("[Polling] Cliente desconectado, intentando reconectar...")
                    if await reconnect_client():
                        consecutive_failures = 0
                        logger.info("[Polling] Reconectado, forzando ciclo de polling ahora")
                    else:
                        consecutive_failures += 1
                        backoff = min(5 * (2 ** (consecutive_failures - 1)), 120)
                        await asyncio.sleep(backoff)
                        continue

                msgs = await client.get_messages(CHANNEL_SRC_ENTITY, limit=limit)

                if msgs:
                    csv_ids = get_all_processed_ids()
                    missing_msgs = [msg for msg in msgs if msg.id not in csv_ids]

                    if not FIRST_POLL_DONE:
                        FIRST_POLL_DONE = True
                        logger.info("Primer ciclo: registrando historial sin procesar.")
                        for m in msgs:
                            await save_message_to_csv(m.id, m.message)
                            PROCESSED_MESSAGES.add(m.id)
                            if m.id > last_processed_id:
                                last_processed_id = m.id
                        save_last_processed_id(last_processed_id)
                    else:
                        if missing_msgs:
                            logger.info(f"[Polling] {len(missing_msgs)} mensajes faltantes. Procesando.")
                            for m in sorted(missing_msgs, key=lambda x: x.id):
                                if m.id not in PROCESSED_MESSAGES:
                                    await process_message(m, is_fetched=True)
                                    PROCESSED_MESSAGES.add(m.id)
                                    if m.id > last_processed_id:
                                        last_processed_id = m.id
                                        save_last_processed_id(last_processed_id)
                        else:
                            now = time.time()
                            if now - last_all_clear_log >= 300:
                                logger.info("Todo en orden, seguimos escuchando...")
                                last_all_clear_log = now

                consecutive_failures = 0

            except Exception as e:
                consecutive_failures += 1
                backoff = min(5 * (2 ** (consecutive_failures - 1)), 120)
                logger.error(f"[Polling] Error ({consecutive_failures}): {e}. Reintento en {backoff}s")
                await asyncio.sleep(backoff)
                continue

            await asyncio.sleep(interval)

    # Iniciar polling en background
    asyncio.create_task(poll_missing_messages())

    logger.info(f"Escuchando canal {SIGNAL_CHANNEL} y reenviando a {FORWARD_CHAT_ID}")
    logger.info("=== INICIO DEL MODULO DE RECONEXIÓN ===")

    # Bucle principal: mantener el cliente vivo
    retry_delay = 5
    connection_attempt = 0

    while True:
        try:
            await client.run_until_disconnected()
            logger.info("Cliente desconectado intencionalmente, terminando.")
            break
        except Exception as e:
            connection_attempt += 1
            backoff = min(retry_delay * (2 ** (connection_attempt - 1)), 300)
            logger.error(f"[RECONEXION] Intento {connection_attempt}: {e}. Espera {backoff}s")
            await asyncio.sleep(backoff)

            if await reconnect_client():
                connection_attempt = 0


if __name__ == "__main__":
    asyncio.run(main())