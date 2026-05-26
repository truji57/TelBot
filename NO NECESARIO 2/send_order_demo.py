#!/usr/bin/env python
"""
Demo: envío de una orden a MetaTrader 5 mediante mt5_connector.

Uso rápido:
    DRY_RUN=true python send_order_demo.py   # simula sin ejecutar
    python send_order_demo.py                # envía la orden real
"""

import os
import json
import logging

from config import DRY_RUN  # Si no existe, la variable será None
from mt5_connector import init_mt5, shutdown_mt5, send_order

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Señal de ejemplo (normalmente proviene de signal_parser.py)
# ---------------------------------------------------------------------------
parsed_signal = {
    "is_signal": True,
    "action": "BUY",
    "symbol": "XAUUSD",
    "entry": 2345.50,          # Precio de entrada; usar None para mercado
    "sl": 2340.00,
    "tp": [2352.00, 2358.00],
    "lot_size": None,          # Dejar que el conector calcule el lote
    "notes": "Orden de prueba desde script demo",
}

def main() -> None:
    # Inicializar MT5
    if not init_mt5():
        logger.error("No se pudo conectar a MetaTrader 5.")
        return

    # Si está activado el modo simulación, simplemente imprimimos lo que se enviaría
    if os.getenv("DRY_RUN", "").lower() == "true":
        logger.info("[DRY_RUN] Simulación – no se enviará la orden a MT5.")
        logger.info(json.dumps(parsed_signal, indent=2, ensure_ascii=False))
        shutdown_mt5()
        return

    # Enviar la orden real
    result = send_order(parsed_signal)
    if result.get("success"):
        logger.info(f"Orden enviada con éxito – ticket: {result.get('ticket')}")
    else:
        logger.error(f"Error al enviar la orden – retcode: {result.get('retcode')}, mensaje: {result.get('message')}")

    # Cerrar la conexión
    shutdown_mt5()

if __name__ == "__main__":
    main()
