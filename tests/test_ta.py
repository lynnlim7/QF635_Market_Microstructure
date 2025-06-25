from app.analytics.TradeAnalysis import TradeAnalysis # adjust path
import json
try:
    with open("Trade_history-2024-03-16.json", "r") as f:
        trades = json.load(f)
    print("JSON loaded successfully!")
except json.JSONDecodeError as e:
    print(f"JSON decoding error: {e}")
# trades = json.loads(open(r"C:\Users\coool\qf635_proj\QF635_Market_Microstructure\sample_trade_history.json").read())  # or paste JSON list
bid_ask = {
    "BTCUSDT": {
        "bid": 65845.5,
        "ask": 65869
    }
}

analyzer = TradeAnalysis()
summary = analyzer.get_summary(book_size=100000, trades_json=trades, best_bid_ask=bid_ask)

print(json.dumps(summary, indent=4))