import unittest
from app.common.order_event_update import OrderEventUpdate
from app.portfolio.portfolio_manager import PortfolioManager
from models import ExecutionType, OrderSide, OrderStatus


class TestPortfolioManager(unittest.TestCase):
    def setUp(self):
        self.symbol = 'BTCUSDT'
        self.port = PortfolioManager()

    def test_on_new_trade_buy_and_price_update(self):
        trade = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'BUY',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1,
            'last_price': 100,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }

        # Process trade
        self.port.on_new_trade(trade)

        # Verify position
        stats = self.port.get_portfolio_stats_by_symbol(self.symbol)
        self.assertIsNotNone(stats['position'])
        self.assertAlmostEqual(stats['position']['qty'], 1)
        self.assertAlmostEqual(stats['position']['average_price'], 100)

        price = {
            'contract_name': 'btcusdt',
            'timestamp': 1749875536466,
            'bids': [{'price': 99, 'quantity': 0.256}],
            'asks': [{'price': 101, 'quantity': 0.677}]
        }

        # Process price update
        self.port.on_new_price(price)

        # Verify unrealized PnL
        stats = self.port.get_portfolio_stats_by_symbol(self.symbol)
        self.assertIn(self.symbol, self.port.unrealized_pnl)
        self.assertAlmostEqual(
            stats['unrealized_pnl'],
            -1,  # qty * (best_bid - avg price)
            places=5
        )

    # Add more tests below (examples provided)

    def test_empty_portfolio_on_start(self):
        self.assertEqual(self.port.get_positions(), {})
        self.assertEqual(self.port.get_realized_pnl(), 0.0)

    def test_on_new_trade_sell_and_price_update(self):
        trade = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'SELL',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1,
            'last_price': 100,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }

        # Process trade
        self.port.on_new_trade(trade)

        # Verify position
        stats = self.port.get_portfolio_stats_by_symbol(self.symbol)
        self.assertIsNotNone(stats['position'])
        self.assertAlmostEqual(stats['position']['qty'], -1)
        self.assertAlmostEqual(stats['position']['average_price'], 100)

        price = {
            'contract_name': 'btcusdt',
            'timestamp': 1749875536466,
            'bids': [{'price': 99, 'quantity': 0.256}],
            'asks': [{'price': 102, 'quantity': 0.677}]
        }

        # Process price update
        self.port.on_new_price(price)

        # Verify unrealized PnL
        stats = self.port.get_portfolio_stats_by_symbol(self.symbol)
        self.assertIn(self.symbol, self.port.unrealized_pnl)
        self.assertAlmostEqual(
            stats['unrealized_pnl'],
            -2,
            places=5
        )

    def test_2_buy_orders(self):
        trade = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'BUY',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1,
            'last_price': 99,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }
        trade1 = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'BUY',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1,
            'last_price': 101,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }

        # Process trade
        self.port.on_new_trade(trade)
        self.port.on_new_trade(trade1)


        # Verify position
        stats = self.port.get_portfolio_stats_by_symbol(self.symbol)
        self.assertIsNotNone(stats['position'])
        self.assertAlmostEqual(stats['position']['qty'], 2)
        self.assertAlmostEqual(stats['position']['average_price'], 100)

    def test_1_buy_order_1_sell_order_less_than_buy(self):
        trade = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'BUY',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1,
            'last_price': 99,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }
        trade1 = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'SELL',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 0.5,
            'last_price': 101,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }

        # Process trade
        self.port.on_new_trade(trade)
        self.port.on_new_trade(trade1)


        # Verify position
        stats = self.port.get_portfolio_stats_by_symbol(self.symbol)
        self.assertIsNotNone(stats['position'])
        self.assertAlmostEqual(stats['position']['qty'], 0.5)
        self.assertAlmostEqual(stats['position']['average_price'], 99)
        self.assertAlmostEqual(stats['realized_pnl'], 1)


    def test_1_buy_order_1_sell_order_equal_to_buy(self):
        trade = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'BUY',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1,
            'last_price': 99,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }
        trade1 = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'SELL',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1,
            'last_price': 101,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }

        # Process trade
        self.port.on_new_trade(trade)
        self.port.on_new_trade(trade1)


        # Verify position
        stats = self.port.get_portfolio_stats_by_symbol(self.symbol)
        self.assertIsNotNone(stats['position'])
        self.assertAlmostEqual(stats['position']['qty'], 0)
        self.assertAlmostEqual(stats['position']['average_price'], 0)
        self.assertAlmostEqual(stats['realized_pnl'], 2)


    def test_1_buy_order_1_sell_order_greater_than_buy(self):
        trade = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'BUY',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1,
            'last_price': 99,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }
        trade1 = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'SELL',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1.5,
            'last_price': 101,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }

        # Process trade
        self.port.on_new_trade(trade)
        self.port.on_new_trade(trade1)


        # Verify position
        stats = self.port.get_portfolio_stats_by_symbol(self.symbol)
        self.assertIsNotNone(stats['position'])
        self.assertAlmostEqual(stats['position']['qty'], -0.5)
        self.assertAlmostEqual(stats['position']['average_price'], 101)
        self.assertAlmostEqual(stats['realized_pnl'], 2)

    def test_2_sell_orders(self):
        trade = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'SELL',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1,
            'last_price': 99,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }
        trade1 = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'SELL',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1,
            'last_price': 101,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }

        # Process trade
        self.port.on_new_trade(trade)
        self.port.on_new_trade(trade1)

        # Verify position
        stats = self.port.get_portfolio_stats_by_symbol(self.symbol)
        self.assertIsNotNone(stats['position'])
        self.assertAlmostEqual(stats['position']['qty'], -2)
        self.assertAlmostEqual(stats['position']['average_price'], 100)
        # self.assertAlmostEqual(stats['realized_pnl'], 2)


    def test_1_sell_order_1_buy_order_less_than_sell(self):
        trade = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'SELL',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1,
            'last_price': 99,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }
        trade1 = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'BUY',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 0.5,
            'last_price': 101,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }

        # Process trade
        self.port.on_new_trade(trade)
        self.port.on_new_trade(trade1)

        # Verify position
        stats = self.port.get_portfolio_stats_by_symbol(self.symbol)
        self.assertIsNotNone(stats['position'])
        self.assertAlmostEqual(stats['position']['qty'], -0.5)
        self.assertAlmostEqual(stats['position']['average_price'], 99)
        self.assertAlmostEqual(stats['realized_pnl'], -1)

    def test_1_sell_order_1_buy_order_eq_to_sell(self):
        trade = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'SELL',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1,
            'last_price': 99,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }
        trade1 = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'BUY',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1,
            'last_price': 101,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }

        # Process trade
        self.port.on_new_trade(trade)
        self.port.on_new_trade(trade1)

        # Verify position
        stats = self.port.get_portfolio_stats_by_symbol(self.symbol)
        self.assertIsNotNone(stats['position'])
        self.assertAlmostEqual(stats['position']['qty'], 0.0)
        self.assertAlmostEqual(stats['position']['average_price'], 0.0)
        self.assertAlmostEqual(stats['realized_pnl'], -2)


    def test_1_sell_order_1_buy_order_greater_than_sell(self):
        trade = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'SELL',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1,
            'last_price': 99,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }
        trade1 = {
            'symbol': self.symbol,
            'order_id': 4525164108,
            'client_order_id': 'web_EFSZLtm94RjlFphDNKLg',
            'side': 'BUY',
            'position_side': 'BOTH',
            'exec_type': ExecutionType.TRADE.name,
            'status': OrderStatus.FILLED.name,
            'order_type': 'MARKET',
            'time_in_force': 'GTC',
            'orig_qty': 1,
            'cum_filled_qty': 1,
            'avg_price': 100,
            'last_qty': 1.5,
            'last_price': 101,
            'commission': 0.04212276,
            'realized_pnl': 0.48545,
            'is_maker': False,
            'event_time_ms': 1749876626477,
            'trade_time_ms': 1749876626476,
            'stop_price': 0.0,
            'activation_price': 0.0,
            'callback_rate': 0.0
        }

        # Process trade
        self.port.on_new_trade(trade)
        self.port.on_new_trade(trade1)

        # Verify position
        stats = self.port.get_portfolio_stats_by_symbol(self.symbol)
        self.assertIsNotNone(stats['position'])
        self.assertAlmostEqual(stats['position']['qty'], 0.5)
        self.assertAlmostEqual(stats['position']['average_price'], 101)
        self.assertAlmostEqual(stats['realized_pnl'], -2)




if __name__ == "__main__":
    unittest.main()
