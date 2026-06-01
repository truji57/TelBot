'''mt5_connector.py
Módulo para conectar a MetaTrader 5, traducir símbolos según el broker y enviar órdenes.

Requisitos:
- ``MetaTrader5`` (ya está en ``requirements.txt``)
- ``risk_manager`` para cálculo de lotes y tipo de orden.
- ``config`` con credenciales y nombre del servidor (``MT5_SERVER``).
- ``symbols_map.yaml`` en la raíz del proyecto que contiene el mapeo
  estándar → broker‑específico.

El archivo ``symbols_map.yaml`` tiene la forma:

XAUUSD:
  BlueWhaleMarkets-Server: "XAUUSD.pro"
  ICMarketsSC-Demo: "XAUUSD"
  ...

El conector carga este mapa una sola vez y, para cada símbolo solicitado,
intenta encontrar la variante correspondiente al servidor configurado. Si no
encuentra un mapping, usa el símbolo tal cual.
'''

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

import MetaTrader5 as mt5  # type: ignore

from config import (
    MT5_LOGIN,
    MT5_PASSWORD,
    MT5_SERVER,
    MT5_TERMINAL_PATH,
    MT5_INSTANCE_ID,
    DEFAULT_MAGIC,
)
from risk_manager import (
    calcular_lotes,
    determine_order_type,
    build_trade_summary,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Carga del mapa de símbolos
# ---------------------------------------------------------------------------
_SYMBOL_MAP: Dict[str, Dict[str, str]] = {}

def _load_symbol_map() -> None:
    """Carga ``symbols_map.yaml`` en la variable global ``_SYMBOL_MAP``.

    El archivo tiene un formato muy simple y no requiere PyYAML; se parsea
    manualmente para evitar dependencias externas.
    """
    global _SYMBOL_MAP
    path = Path(__file__).with_name("symbols_map.yaml")
    if not path.is_file():
        logger.warning("symbols_map.yaml no encontrado; se usará el símbolo tal cual.")
        _SYMBOL_MAP = {}
        return
    current_symbol: Optional[str] = None
    with path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue
            # Líneas sin sangría son símbolos base
            if not line.startswith(" ") and not line.startswith("\t"):
                current_symbol = line.split("#")[0].strip().rstrip(":")
                _SYMBOL_MAP[current_symbol] = {}
            else:
                # línea indented: "Broker: \"Symbol\""
                if current_symbol is None:
                    continue
                parts = line.strip().split(":", 1)
                if len(parts) != 2:
                    continue
                broker = parts[0].strip()
                symbol_val = parts[1].strip().strip('"').strip("'")
                _SYMBOL_MAP[current_symbol][broker] = symbol_val
    logger.debug(f"Símbolos cargados: {_SYMBOL_MAP}")

_load_symbol_map()

# ---------------------------------------------------------------------------
# Obtención del modo de llenado (filling mode) compatible
# ---------------------------------------------------------------------------
def _get_filling_mode(symbol: str) -> int:
    """Devuelve el modo de llenado soportado por el broker para *symbol*.
    Usa la información del símbolo (trade_filling) cuando está disponible.
    Si no se encuentra, devuelve ``mt5.ORDER_FILLING_RETURN`` como fallback.
    """
    try:
        info = mt5.symbol_info(symbol)
        if info and hasattr(info, "trade_filling") and info.trade_filling:
            return info.trade_filling
    except Exception as e:
        logger.debug(f"No se pudo obtener trade_filling para {symbol}: {e}")
    return mt5.ORDER_FILLING_RETURN

def _translate_symbol(symbol: str) -> str:
    """Devuelve la representación del símbolo para el broker actual.

    Primero busca en ``symbols_map.yaml`` (con match exacto y luego
    case‑insensitive). Si no encuentra, consulta los símbolos disponibles
    en MT5 y busca por prefijo (p.ej. XAUUSD → XAUUSD.raw).
    """
    broker_map = _SYMBOL_MAP.get(symbol)
    if broker_map:
        mapped = broker_map.get(MT5_SERVER)
        if mapped:
            logger.debug(f"Mapeo de símbolo: {symbol} → {mapped} (broker {MT5_SERVER})")
            return mapped
        server_lower = MT5_SERVER.lower()
        for broker_key, broker_val in broker_map.items():
            if broker_key.lower() == server_lower:
                logger.debug(f"Mapeo de símbolo (case-insensitive): {symbol} → {broker_val} (broker {MT5_SERVER})")
                return broker_val

    # Fallback: buscar en MT5 símbolos disponibles
    try:
        mt5_symbols = mt5.symbols_get()
        if mt5_symbols:
            mt5_names = {s.name for s in mt5_symbols}
            if symbol in mt5_names:
                return symbol
            prefix_lower = symbol.lower()
            for mt5_name in mt5_names:
                if mt5_name.lower().startswith(prefix_lower):
                    logger.debug(f"Auto-detección de símbolo: {symbol} → {mt5_name}")
                    return mt5_name
    except Exception as e:
        logger.debug(f"Auto-detección de símbolo falló: {e}")

    return symbol

# ---------------------------------------------------------------------------
# Conexión/Desconexión a MT5
# ---------------------------------------------------------------------------
def init_mt5() -> bool:
    """Inicializa la conexión con MetaTrader 5.

    Usa ``MT5_TERMINAL_PATH`` si está definido, de lo contrario confía en la
    ruta por defecto del sistema. Después de ``initialize`` se llama a ``login``
    con las credenciales provistas en ``config.py``.
    """
    init_kwargs: Dict[str, Any] = {}
    if MT5_TERMINAL_PATH:
        init_kwargs["path"] = MT5_TERMINAL_PATH
    if not mt5.initialize(**init_kwargs):
        logger.error(f"Error al iniciar MT5: {mt5.last_error()}")
        return False
    # login
    if not mt5.login(
        int(MT5_LOGIN), password=MT5_PASSWORD, server=MT5_SERVER, timeout=30
    ):
        logger.error(f"Error al loguearse en MT5: {mt5.last_error()}")
        mt5.shutdown()
        return False
    logger.info("Conexión a MT5 establecida correctamente.")
    return True

def shutdown_mt5() -> None:
    """Cierra la sesión de MT5 de forma segura."""
    mt5.shutdown()
    logger.info("MT5 shutdown completed.")

# ---------------------------------------------------------------------------
# Envío de órdenes
# ---------------------------------------------------------------------------
def send_order(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Envía una orden a MT5 basada en la señal parseada.

    Parámetros esperados en ``parsed`` (según ``signal_parser``)::
        {
            "action": "BUY"|"SELL",
            "symbol": "XAUUSD",
            "entry": float | null,
            "sl": float,
            "tp": [float, ...],
            "lot_size": null | float,
            "notes": "..."
        }
    """
    # --- Preparación básica -------------------------------------------------
    action = parsed.get("action", "").upper()
    base_symbol = parsed.get("symbol")
    if not action or not base_symbol:
        raise ValueError("Parsed signal must contain 'action' and 'symbol'.")

    symbol = _translate_symbol(base_symbol)
    entry = parsed.get("entry")  # puede ser None (market)
    sl = parsed.get("sl")
    tp_list: List[float] = parsed.get("tp", [])
    # tomamos el ÚLTIMO TP de la lista (TP2 o TP3 si existen)
    tp = tp_list[-1] if tp_list else 0.0

    # --- Cálculo del lote (si no está provisto) ---------------------------
    lot = parsed.get("lot_size")
    if lot is None:
        # Necesitamos balance; usamos el balance actual de la cuenta
        account_info = mt5.account_info()
        if account_info is None:
            raise RuntimeError("No se pudo obtener la info de la cuenta MT5.")
        balance = account_info.balance
        # Si entry es None, usamos precio actual para cálculo de distancia SL
        if entry is None:
            entry_price = _get_current_price(symbol)
            if entry_price is None:
                raise RuntimeError("No se pudo determinar el precio actual para cálculo de lote.")
        else:
            entry_price = entry
        lot = calcular_lotes(symbol, balance, entry_price, sl)

    # --- Tipo de orden -----------------------------------------------------
    order_type_str = determine_order_type(action, entry, symbol)
    if order_type_str == "market":
        order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
        price = 0.0  # price no se usa para market orders
        trade_action = mt5.TRADE_ACTION_DEAL
    elif order_type_str == "limit":
        order_type = mt5.ORDER_TYPE_BUY_LIMIT if action == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT
        price = entry if entry is not None else 0.0
        trade_action = mt5.TRADE_ACTION_PENDING
    elif order_type_str == "stop":
        order_type = mt5.ORDER_TYPE_BUY_STOP if action == "BUY" else mt5.ORDER_TYPE_SELL_STOP
        price = entry if entry is not None else 0.0
        trade_action = mt5.TRADE_ACTION_PENDING
    else:
        raise ValueError(f"Tipo de orden desconocido: {order_type_str}")

    # --- Construcción del request ------------------------------------------
    request: Dict[str, Any] = {
        "action": trade_action,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": DEFAULT_MAGIC,
        "comment": f"BotSignal {action} {base_symbol}",
        "type_filling": None,  # will be set in loop (filled later)
        "type_time": mt5.ORDER_TIME_GTC,
    }

    logger.info(build_trade_summary(parsed, lot, order_type_str))

    # Verificar que el símbolo existe y está habilitado en Market Watch
    if not mt5.symbol_select(symbol, True):
        logger.warning(f"No se pudo seleccionar/habilitar {symbol} en Market Watch")

    # Intentamos varios modos de llenado (filling) hasta que la orden sea aceptada.
    filling_modes = [
        _get_filling_mode(symbol),
        mt5.ORDER_FILLING_RETURN,
        mt5.ORDER_FILLING_FOK,
        mt5.ORDER_FILLING_IOC,
    ]
    # Eliminar duplicados y valores None
    filling_modes = [m for i, m in enumerate(filling_modes) if m is not None and m not in filling_modes[:i]]

    for filling in filling_modes:
        request["type_filling"] = filling
        logger.info(f"Intentando enviar orden con filling mode {filling} para {symbol}")
        result = mt5.order_send(request)
        if result is None:
            logger.warning(f"order_send devolvió None con filling {filling}")
            continue
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(
                f"Orden ejecutada con éxito: {action} {symbol} lot={lot} price={price} sl={sl} tp={tp} "
                f"filling={filling} ticket={result.order}"
            )
            return {"success": True, "order": result.order, "ticket": result.order}
        else:
            retcode_desc = _mt5_error_description(result.retcode)
            logger.warning(
                f"Fallo al ejecutar orden con filling {filling}: retcode={result.retcode} ({retcode_desc}), message={result.comment}"
            )
    # Si llegamos aquí, todos los intentos fallaron
    logger.error(f"Todos los modos de filling fallaron para {symbol}")
    last_err = result.comment if result else "order_send returned None"
    last_retcode = result.retcode if result else None
    return {"success": False, "retcode": last_retcode, "message": f"{last_err} (retcode {last_retcode}: {_mt5_error_description(last_retcode)})"}

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------
_MT5_ERROR_CODES = {
    10004: "TRADE_RETCODE_DONE (orden ejecutada)",
    10006: "TRADE_RETCODE_REQUOTE (cotización rechazada)",
    10007: "TRADE_RETCODE_REJECT (orden rechazada)",
    10008: "TRADE_RETCODE_CANCEL (orden cancelada)",
    10009: "TRADE_RETCODE_PLACED (orden pendiente colocada)",
    10010: "TRADE_RETCODE_DONE_PARTIAL (ejecución parcial)",
    10011: "TRADE_RETCODE_ERROR (error de ejecución)",
    10012: "TRADE_RETCODE_TIMEOUT (timeout)",
    10013: "TRADE_RETCODE_INVALID (parametros inválidos)",
    10014: "TRADE_RETCODE_INVALID_VOLUME (volumen inválido)",
    10015: "TRADE_RETCODE_INVALID_PRICE (precio inválido)",
    10016: "TRADE_RETCODE_INVALID_STOPS (stops inválidos)",
    10017: "TRADE_RETCODE_TRADE_DISABLED (trading deshabilitado)",
    10018: "TRADE_RETCODE_MARKET_CLOSED (mercado cerrado)",
    10019: "TRADE_RETCODE_NO_MONEY (fondos insuficientes)",
    10020: "TRADE_RETCODE_PRICE_CHANGED (precio cambiado)",
    10021: "TRADE_RETCODE_PRICE_OFF (precio fuera de límites)",
    10022: "TRADE_RETCODE_INVALID_EXPIRATION (expiración inválida)",
    10023: "TRADE_RETCODE_ORDER_CHANGED (orden cambiada)",
    10024: "TRADE_RETCODE_TOO_MANY_REQUESTS (demasiadas solicitudes)",
    10025: "TRADE_RETCODE_NO_CHANGES (sin cambios)",
    10026: "TRADE_RETCODE_SERVER_DISABLES_AT (AT deshabilitado por servidor)",
    10027: "TRADE_RETCODE_CLIENT_DISABLES_AT (AT deshabilitado por cliente)",
    10028: "TRADE_RETCODE_LOCKED (orden bloqueada)",
    10029: "TRADE_RETCODE_FROZEN (orden congelada)",
    10030: "TRADE_RETCODE_INVALID_FILL (tipo de llenado inválido)",
    10031: "TRADE_RETCODE_CONNECTION (sin conexión al servidor)",
    10032: "TRADE_RETCODE_ONLY_REAL (solo cuentas reales)",
    10033: "TRADE_RETCODE_LIMIT_ORDERS (límite de órdenes alcanzado)",
    10034: "TRADE_RETCODE_LIMIT_VOLUME (límite de volumen alcanzado)",
}

def _mt5_error_description(retcode):
    if retcode is None:
        return "DESCONOCIDO"
    return _MT5_ERROR_CODES.get(retcode, f"CODIGO_NO_RECONOCIDO_{retcode}")

def _get_current_price(symbol: str) -> Optional[float]:
    """Obtiene el precio medio (bid+ask)/2 del símbolo."""
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return None
    if tick.bid and tick.ask:
        return (tick.bid + tick.ask) / 2.0
    return tick.bid or tick.ask

# Exportar nombres principales para ``from mt5_connector import *``
__all__ = [
    "init_mt5",
    "shutdown_mt5",
    "send_order",
    "_translate_symbol",
]

# ---------------------------------------------------------------------------
# Funciones para control de posiciones y órdenes (comandos)
# ---------------------------------------------------------------------------

def get_account_status() -> Dict[str, Any]:
    """Devuelve estado actual de la cuenta MT5."""
    info = mt5.account_info()
    if info is None:
        return {"error": "No se pudo obtener información de la cuenta"}
    
    positions = mt5.positions_get()
    if positions is None:
        positions = []
    
    orders = mt5.orders_get()
    if orders is None:
        orders = []
    
    total_profit = sum(p.profit for p in positions)
    
    return {
        "balance": info.balance,
        "equity": info.equity,
        "margin": info.margin,
        "margin_free": info.margin_free,
        "profit": total_profit,
        "positions": len(positions),
        "pending_orders": len(orders),
        "server": info.server,
        "currency": info.currency,
        "login": info.login,
    }


def close_all_positions() -> List[Dict[str, Any]]:
    """Cierra todas las posiciones abiertas."""
    positions = mt5.positions_get()
    if not positions:
        return [{"success": False, "message": "No hay posiciones abiertas"}]
    
    results = []
    for pos in positions:
        ticket = pos.ticket
        symbol = pos.symbol
        volume = pos.volume
        pos_type = pos.type
        
        price = mt5.symbol_info_tick(symbol).bid if pos_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_SELL if pos_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
            "position": ticket,
            "price": price,
            "deviation": 10,
            "magic": DEFAULT_MAGIC,
            "comment": "Close by Bot",
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Posición cerrada: ticket={ticket} {symbol}")
            results.append({"success": True, "ticket": ticket, "symbol": symbol})
        else:
            err_msg = _mt5_error_description(result.retcode) if result else "order_send returned None"
            logger.warning(f"Error al cerrar {ticket}: {err_msg}")
            results.append({"success": False, "ticket": ticket, "symbol": symbol, "error": err_msg})
    
    return results


def delete_all_pending_orders() -> List[Dict[str, Any]]:
    """Elimina todas las órdenes pendientes."""
    orders = mt5.orders_get()
    if not orders:
        return [{"success": False, "message": "No hay órdenes pendientes"}]
    
    results = []
    for order in orders:
        ticket = order.ticket
        
        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket,
        }
        
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"Orden pendiente eliminada: ticket={ticket}")
            results.append({"success": True, "ticket": ticket})
        else:
            err_msg = _mt5_error_description(result.retcode) if result else "order_send returned None"
            logger.warning(f"Error al eliminar orden {ticket}: {err_msg}")
            results.append({"success": False, "ticket": ticket, "error": err_msg})
    
    return results


def set_breakeven_all() -> List[Dict[str, Any]]:
    """Mueve el SL de todas las posiciones abiertas al precio de entrada."""
    positions = mt5.positions_get()
    if not positions:
        return [{"success": False, "message": "No hay posiciones abiertas"}]
    
    results = []
    for pos in positions:
        ticket = pos.ticket
        symbol = pos.symbol
        entry_price = pos.price_open
        volume = pos.volume
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": symbol,
            "position": ticket,
            "sl": entry_price,
            "tp": pos.tp,
            "magic": DEFAULT_MAGIC,
            "comment": "Breakeven by Bot",
        }
        
        result = mt5.order_send(request)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"SL movido a breakeven: ticket={ticket} {symbol} @ {entry_price}")
            results.append({"success": True, "ticket": ticket, "symbol": symbol, "sl": entry_price})
        else:
            err_msg = _mt5_error_description(result.retcode) if result else "order_send returned None"
            logger.warning(f"Error al mover SL de {ticket}: {err_msg}")
            results.append({"success": False, "ticket": ticket, "symbol": symbol, "error": err_msg})
    
    return results


def get_open_positions() -> List[Dict[str, Any]]:
    """Devuelve lista detallada de posiciones abiertas."""
    positions = mt5.positions_get()
    if not positions:
        return []

    result = []
    for pos in positions:
        tick = mt5.symbol_info_tick(pos.symbol)
        current_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask if tick else 0

        result.append({
            "ticket": pos.ticket,
            "symbol": pos.symbol,
            "type": "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
            "volume": pos.volume,
            "entry": pos.price_open,
            "sl": pos.sl,
            "tp": pos.tp,
            "current_price": current_price,
            "profit": pos.profit,
            "swap": pos.swap,
            "commission": pos.commission,
            "magic": pos.magic,
            "comment": pos.comment,
        })
    return result


def get_pending_orders() -> List[Dict[str, Any]]:
    """Devuelve lista detallada de órdenes pendientes."""
    orders = mt5.orders_get()
    if not orders:
        return []

    type_map = {
        mt5.ORDER_TYPE_BUY_LIMIT: "BUY_LIMIT",
        mt5.ORDER_TYPE_SELL_LIMIT: "SELL_LIMIT",
        mt5.ORDER_TYPE_BUY_STOP: "BUY_STOP",
        mt5.ORDER_TYPE_SELL_STOP: "SELL_STOP",
    }

    result = []
    for order in orders:
        result.append({
            "ticket": order.ticket,
            "symbol": order.symbol,
            "type": type_map.get(order.type, f"UNKNOWN_{order.type}"),
            "volume": order.volume,
            "price": order.price,
            "sl": order.sl,
            "tp": order.tp,
            "expiration": order.expiration,
            "comment": order.comment,
            "magic": order.magic,
        })
    return result


def close_position_by_symbol(symbol: str) -> Dict[str, Any]:
    """Cierra una posición abierta por símbolo."""
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return {"success": False, "message": f"No hay posiciones abiertas para {symbol}"}

    pos = positions[0]
    ticket = pos.ticket
    volume = pos.volume
    pos_type = pos.type

    price = mt5.symbol_info_tick(symbol).bid if pos_type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_SELL if pos_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
        "position": ticket,
        "price": price,
        "deviation": 10,
        "magic": DEFAULT_MAGIC,
        "comment": "Close by Bot",
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"Posición cerrada: {symbol} ticket={ticket}")
        return {"success": True, "ticket": ticket, "symbol": symbol}

    err_msg = _mt5_error_description(result.retcode) if result else "order_send returned None"
    return {"success": False, "symbol": symbol, "error": err_msg}


def modify_position_sl(symbol: str, sl_price: float) -> Dict[str, Any]:
    """Modifica el SL de una posición abierta por símbolo."""
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return {"success": False, "message": f"No hay posiciones abiertas para {symbol}"}

    pos = positions[0]
    ticket = pos.ticket

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": symbol,
        "position": ticket,
        "sl": sl_price,
        "tp": pos.tp,
        "magic": DEFAULT_MAGIC,
        "comment": "Modify SL by Bot",
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"SL modificado: {symbol} ticket={ticket} sl={sl_price}")
        return {"success": True, "ticket": ticket, "symbol": symbol, "sl": sl_price}

    err_msg = _mt5_error_description(result.retcode) if result else "order_send returned None"
    return {"success": False, "symbol": symbol, "error": err_msg}


def modify_position_tp(symbol: str, tp_price: float) -> Dict[str, Any]:
    """Modifica el TP de una posición abierta por símbolo."""
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return {"success": False, "message": f"No hay posiciones abiertas para {symbol}"}

    pos = positions[0]
    ticket = pos.ticket

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": symbol,
        "position": ticket,
        "sl": pos.sl,
        "tp": tp_price,
        "magic": DEFAULT_MAGIC,
        "comment": "Modify TP by Bot",
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(f"TP modificado: {symbol} ticket={ticket} tp={tp_price}")
        return {"success": True, "ticket": ticket, "symbol": symbol, "tp": tp_price}

    err_msg = _mt5_error_description(result.retcode) if result else "order_send returned None"
    return {"success": False, "symbol": symbol, "error": err_msg}
