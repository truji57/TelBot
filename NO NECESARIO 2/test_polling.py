#!/usr/bin/env python3
import csv
import os

# Simular el comportamiento del polling con datos de prueba
def test_polling_logic():
    # Crear archivo CSV de prueba
    MESSAGES_CSV_FILE = "processed_messages.csv"

    # Limpiar archivo si existe
    if os.path.exists(MESSAGES_CSV_FILE):
        os.remove(MESSAGES_CSV_FILE)

    # Crear algunos mensajes de prueba
    test_messages = [
        (1001, "Mensaje 1", "2026-05-25 10:00:00"),
        (1002, "Mensaje 2", "2026-05-25 10:01:00"),
        (1003, "Mensaje 3", "2026-05-25 10:02:00"),
    ]

    # Escribir mensajes en CSV
    with open(MESSAGES_CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['message_id', 'text', 'timestamp'])
        writer.writerows(test_messages)

    # Simular obtener mensajes del canal (con uno más nuevo)
    channel_messages = [
        {"id": 1001, "text": "Mensaje 1"},
        {"id": 1002, "text": "Mensaje 2"},
        {"id": 1004, "text": "Mensaje 4 (nuevo)"}  # Este debería detectarse como faltante
    ]

    # Obtener mensajes del CSV
    csv_messages = []
    if os.path.exists(MESSAGES_CSV_FILE):
        with open(MESSAGES_CSV_FILE, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader)  # Saltar encabezado
            for row in reader:
                if len(row) >= 1:
                    try:
                        msg_id = int(row[0])
                        csv_messages.append((msg_id, row[1]))
                    except:
                        continue

    csv_ids = {msg[0] for msg in csv_messages}

    # Encontrar mensajes faltantes
    missing_msgs = [msg for msg in channel_messages if msg["id"] not in csv_ids]

    print(f"Mensajes en canal: {[m['id'] for m in channel_messages]}")
    print(f"Mensajes en CSV: {list(csv_ids)}")
    print(f"Mensajes faltantes: {[m['id'] for m in missing_msgs]}")

    if missing_msgs:
        print(f"OK: Se encontraron {len(missing_msgs)} mensajes faltantes. Procesando...")
        for m in sorted(missing_msgs, key=lambda x: x["id"]):
            print(f"   - Procesando mensaje ID: {m['id']} - {m['text']}")
    else:
        print("OK: Todo en orden. No hay mensajes faltantes.")

if __name__ == "__main__":
    test_polling_logic()