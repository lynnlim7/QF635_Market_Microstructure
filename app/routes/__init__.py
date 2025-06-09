from flask import jsonify, request

from app.api.binance_api import BinanceApi
from app.common.interface_order import Side

#TODO : implement kill switch route  

def register_routes(app, binance_api:BinanceApi):
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