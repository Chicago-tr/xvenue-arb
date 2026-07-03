import asyncio
import json
import time
from datetime import datetime

import requests

time1 = time.time()
result = requests.get("https://api.binance.us/api/v3/ticker/bookTicker?symbol=BTCUSD")
time2 = time.time()
print(time1, time2)
print(result.elapsed)
