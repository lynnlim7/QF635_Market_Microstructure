import unittest
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
from binance.client import Client
from bot.client.binance_api import BinanceApi
from bot.strategy.macd_strategy import MACDStrategy

class TestMACDStrategy(unittest.TestCase):
    def setUp(self):
        self.api_mock = MagicMock(spec=BinanceApi)
        # Simulated data for testing (sample close prices)
        mock_data = {
            "timestamp": [1, 2, 3, 4, 5, 6],
            "close": [45000, 46000, 45500, 47000, 46500, 46000],
            "volume": [100, 200, 150, 100, 200, 150],
        }
        self.api_mock.get_close_prices_df.return_value = pd.DataFrame(mock_data)
        # Instantiate MACDStrategy
        self.strategy = MACDStrategy(symbol="BTCUSDT", api=self.api_mock)

    def test_initialise_data(self):
        self.strategy.initialise_data()

        self.assertIn('MACD', self.strategy.data.columns)
        self.assertIn('Signal_Line', self.strategy.data.columns)

        expected_macd = np.float64(307.06404401960026)
        expected_signal_line = np.float64(156.76272976173144)

        # Verify the initial MACD and Signal Line values
        self.assertEqual(self.strategy.latest_macd, expected_macd)
        self.assertEqual(self.strategy.latest_signal_line, expected_signal_line)

    def test_update_data(self):
        new_candle = {"timestamp": 7, "close": 47000, "volume": 100}
        self.strategy.update_data(new_candle)

        self.assertEqual(len(self.strategy.data), 7)

        expected_macd = np.float64(388.43071318312286)
        expected_signal_line = np.float64(203.09632644600975)

        # Verify the initial MACD and Signal Line values
        self.assertEqual(self.strategy.latest_macd, expected_macd)
        self.assertEqual(self.strategy.latest_signal_line, expected_signal_line)

    def test_update_data_duplicate_data(self):
        new_candle = {"timestamp": 7, "close": 47000, "volume": 100}
        self.strategy.update_data(new_candle)

        self.assertEqual(len(self.strategy.data), 7)

        expected_macd = np.float64(388.43071318312286)
        expected_signal_line = np.float64(203.09632644600975)

        # Verify the initial MACD and Signal Line values
        self.assertEqual(self.strategy.latest_macd, expected_macd)
        self.assertEqual(self.strategy.latest_signal_line, expected_signal_line)

    def test_generate_signal_buy(self):
        self.strategy.latest_macd = 100
        self.strategy.latest_signal_line = 50

        signal = self.strategy.generate_signal()
        self.assertEqual(signal, 1)  # Buy signal

    def test_generate_signal_sell(self):
        self.strategy.latest_macd = 50
        self.strategy.latest_signal_line = 100

        signal = self.strategy.generate_signal()
        self.assertEqual(signal, -1)

    def test_generate_signal_hold_missing_values(self):
        self.strategy.latest_macd = None
        self.strategy.latest_signal_line = None

        signal = self.strategy.generate_signal()
        self.assertEqual(signal, 0)

    def test_generate_signal_hold(self):
        self.strategy.latest_macd = 100
        self.strategy.latest_signal_line = 90
        self.strategy.last_action = "BUY"

        signal = self.strategy.generate_signal()
        self.assertEqual(signal, 0)

    def test_get_state(self):
        self.strategy.latest_macd = 100
        self.strategy.latest_signal_line = 90
        self.strategy.last_action = "BUY"

        state = self.strategy.get_state()
        self.assertEqual(state["macd"], 100)
        self.assertEqual(state["signal_line"], 90)
        self.assertEqual(state["last_action"], "BUY")

if __name__ == '__main__':
    unittest.main()
