#!/usr/bin/env python3
import sys
sys.path.append('.')
from local_signal_parser import parse_signal

# Mensaje de ejemplo
test_message = """📋 RESUMEN DE OPERACIÓN
  Señal: SELL XAUUSD
  Tipo:  STOP @ 4553.00000
  SL:    4561.00000
  TP1=4550.00000 | TP2=4548.00000 | TP3=4533.00000
  Lots:  1.26
────────────────────────────────────────"""

result = parse_signal(test_message)
print("Resultado:", result)