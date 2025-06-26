from app.analytics.TradeAnalysis import TradeAnalysis # adjust path
import json
import os

DATE = "2024-03-16"

def main():
    print("Current working directory:", os.getcwd())

    trades, port_state = None, None
    try:
        with open(f"tests/sample_data/Trade_history-{DATE}.json", "r") as f:
            trades = json.load(f)
        print("JSON loaded successfully!")
    except json.JSONDecodeError as e:
        print(f"JSON decoding error: {e}")
        return


    try:
        with open(f"tests/sample_data/port-state-{DATE}.json", "r") as f:
            port_state = json.load(f)
        print("JSON loaded successfully!")
    except json.JSONDecodeError as e:
        print(f"JSON decoding error: {e}")
        return


    bid_ask = port_state.get('last_market_price')
    analyzer = TradeAnalysis()
    print(f"trades: {trades}")
    summary = analyzer.get_summary(book_size=100000, trades_json=trades, best_bid_ask=bid_ask)
    print(f"bid_ask: {bid_ask}")
    print(json.dumps(summary, indent=4))


if __name__=="__main__" :
    main()