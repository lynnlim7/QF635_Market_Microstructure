import os
from dotenv import load_dotenv

load_dotenv()

## Binance Testnet Credentials
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

## Scoring Parameters
SIGNAL_SCORE_BUY = 1.0
SIGNAL_SCORE_SELL = -1.0
SIGNAL_SCORE_HOLD = 0

