Este archivo sirve como bloc de notas para registrar tareas pendientes del proyecto. Cada día o cuando sea necesario, anota aquí los próximos pasos, bugs por resolver, mejoras y cualquier objetivo a corto plazo.

## BUGS Y ERRORES
- [x] Error al llegar señal, ha llegado una señal y ha metido esa operacion y otra del dia antes que no deberia de haberla metido
- [x] Si se pierde la conexion a internet, obviamente deja de conectar con telegram pero el bot se detiene, lo correcto seria que estuviese intentando reconectar de nuevo
- [x] Hay veces que no detecta la señal o la manda con demasiado retraso, hay alguna forma de hacer como un barrido cada Xsegundos y comprobar que todos los mensajes de ese canal han sido procesados?
- [x] He probado a quitar conexion, mandar mensaje de prueba y volver a dar conexion, cuando se da cuenta manda el mensaje pero por el log no para de salir constantemente cada ciclo de polling de 15 segundos el mensaje de "Se encontraron 1 mensajes faltantes. Procesando." Y ya estando el mensaje guardado en processed_messages.csv no deberia de salir eso ya que ha sido procesado.
- [x] PENDING_CONFIRMATIONS y ACCOUNT_BALANCE no definidos (NameError)
- [x] signal_parser.py con _split_value duplicada
- [x] Código muerto en mt5_connector.py

# PENDIENTES
- [x] Que tenga en los parametros de .env una bool que active o cd desactive si necesita confirmar trade o no antes de colocar orden y que se confirme por telegram a traves de un boton de si o no y sea capaz de procesar la respuesta del usuario
- [x] Hay mas formatos de mensajes y tiene que admitirlos
- [ ] Que de alguna forma controle si hay una señal mal, que no se haya mandado correctamente los precios o algo de eso
- [ ] IMplementar soporte para multiples TPs, dividir el lotaje en varias cada una con un tp diferente de los que tenga
- [ ] Añadir la opcion de reenviar el mensaje a varios chats ID
- [x] Añadir opcion de activar o desactivar colocar orden y con ello metatrader, por si solo se quiere copiar la señal a otro grupo
 
Mantén este archivo actualizado y revísalo antes de cerrar la sesión.
