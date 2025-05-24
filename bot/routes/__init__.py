from flask import jsonify, request

from bot.common.interface_order import Side


def register_routes(app, gateway_accessor):
    @app.get("/")
    def home():
        return "Welcome to the trading bot!"


    @app.post("/cancel-order")
    def cancel_order():
        gateway = gateway_accessor()

        if gateway is None:
            return jsonify({"error": "Gateway not initialized"}), 503
        try:
            data = request.get_json()
            _order_id = data['orderId']

            result = gateway.cancel_order(
                order_id = _order_id
            )

            return jsonify({"result": result})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.post("/create-order")
    def create_order():
        gateway = gateway_accessor()

        if gateway is None:
            return jsonify({"error": "Gateway not initialized"}), 503

        try:
            data = request.get_json()
            _side = Side[data["side"].upper()]
            _quantity = float(data["quantity"])
            _price = float(data["price"])
            _tif = data["timeInForce"]

            result = gateway.place_limit_order(
                side = _side,
                quantity= _quantity,
                price= _price,
                tif=_tif
            )

            return jsonify(result)
        except Exception as e:
            return jsonify({"error": str(e)}), 500