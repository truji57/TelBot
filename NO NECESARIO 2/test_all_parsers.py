#!/usr/bin/env python3
import sys
sys.path.append('.')
from local_signal_parser import parse_signal

# Test different message formats
test_cases = [
    # Formato estructurado
    """🟢 BUY XAUUSD
  Entry: 4708.24
  TP1: 4724.03
  TP2: 4739.60
  SL: 4695.58""",

    # Formato libre
    """SELL XAUUSD 4696-4700

SL 4704

TP 4693
TP 4691
TP 4685""",

    # Formato de resumen
    """📋 RESUMEN DE OPERACIÓN
  Señal: SELL BTCUSD
  Tipo:  STOP @ 78300.00000
  SL:    78482.00000
  TP1=78124.00000 | TP2=77943.00000 | TP3=77766.00000
  Lots:  0.40""",

    # Mensaje no detectado
    """Este no es una señal de trading, solo un mensaje normal"""
]

print("=== Pruebas del parser ===\n")

for i, message in enumerate(test_cases, 1):
    print(f"--- Caso {i} ---")
    print(message.encode('utf-8'))
    result = parse_signal(message)
    print(f"Resultado: {result}")
    print()
    print("-" * 50)
    print()