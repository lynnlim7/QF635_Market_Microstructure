from flask import jsonify, request

from app.api.binance_api import BinanceApi
from app.common.interface_order import Side
from app.portfolio.portfolio_manager import PortfolioManager


#TODO : implement kill switch route

def register_routes(app, binance_api:BinanceApi, portfolio_manager: PortfolioManager):
    @app.get("/")
    def home():
        return "Welcome to the trading bot!"

    @app.get("/position")
    def get_position():
        if binance_api is None:
            return jsonify({"error": "Gateway not initialized"}), 503
        try:
            result = binance_api.get_current_position()
            return jsonify({"result": result})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.post("/cancel-order")
    def cancel_order():

        if binance_api is None:
            return jsonify({"error": "Gateway not initialized"}), 503
        try:
            data = request.get_json()
            _order_id = data['orderId']

            result = binance_api.cancel_order(
                order_id = _order_id
            )

            return jsonify({"result": result})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.post("/create-order")
    def create_order():
        try:
            data = request.get_json()
            _side = Side[data["side"].upper()]
            _quantity = float(data["quantity"])
            _price = float(data["price"])
            _tif = data["timeInForce"]
            result = binance_api.place_limit_order(
                side = _side,
                quantity= _quantity,
                price= _price,
                tif=_tif
            )

            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.post("/create-market-order")
    def create_market_order():
        try:
            data = request.get_json()
            _side = Side[data["side"].upper()]
            _quantity = float(data["quantity"])
            _price = float(data["price"])
            _tif = data["timeInForce"]
            result = binance_api.place_market_order(
                symbol = "BTCUSDT",
                qty = _quantity,
                side = _side.name,
            )

            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.get("/portfolio_state")
    def get_portfolio_state():
        if portfolio_manager is None:
            return jsonify({"error": "Portfolio managed not initialized"}), 503

        try:
            result = portfolio_manager.get_full_portfolio_state()
            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
