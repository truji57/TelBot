# Stub for MetaTrader5 – solo para el IDE
from typing import Dict, Any, Optional

# Funciones principales
def initialize(path: str = "") -> bool: ...

def login(login: int, password: str, server: str, timeout: int = 30) -> bool: ...

def shutdown() -> None: ...

def order_send(request: Dict[str, Any]) -> Any: ...

def symbol_info(symbol: str) -> Any: ...

def symbol_info_tick(symbol: str) -> Any: ...

def account_info() -> Any: ...

def last_error() -> Any: ...

def symbol_select(symbol: str, enable: bool) -> bool: ...

# Constantes (valores típicos, pueden variar)
ORDER_FILLING_RETURN: int = 0
ORDER_FILLING_IOC: int = 1
ORDER_FILLING_FOK: int = 2
ORDER_FILLING_FILLORKILL: int = 3

ORDER_TYPE_BUY: int = 0
ORDER_TYPE_SELL: int = 1
ORDER_TYPE_BUY_LIMIT: int = 2
ORDER_TYPE_SELL_LIMIT: int = 3
ORDER_TYPE_BUY_STOP: int = 4
ORDER_TYPE_SELL_STOP: int = 5

TRADE_ACTION_DEAL: int = 0
ORDER_TIME_GTC: int = 0
TRADE_RETCODE_DONE: int = 10004
