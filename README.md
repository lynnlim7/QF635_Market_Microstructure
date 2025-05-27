# QF635_Market_Microstructure
# 🤖 Trading Bot 

## 📈 Trading Strategy Implemented in this Project: 


## ✨ Getting Started 
# Steps to run project locally 
- Using `pip`
1. Set up Python virtual environment 
```bash
# Create a virtual environment in the current directory
python3 -m venv .venv

# Activate the virtual environment
# On macOS/Linux:
source .venv/bin/activate

# On Windows (CMD):
.venv\Scripts\activate
```

2. Install project dependencies
```bash
pip install -r requirements.txt
```

- Using `poetry`
1. Install poetry using pipx
```bash
# Install pipx
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Install poetry using pipx 
pipx install poetry
poetry self add poetry-plugin-export 
```

2. Install project dependencies and activate virtual environment
```bash
cd QF635_Market_Microstructure
poetry install
poetry shell

# Add packages 
poetry add <package_name>
# Freeze
poetry export --without-hashes --format=requirements.txt > requirements.txt
```

3. Run project 
```bash
python bot/main.py  # or actual entry point
```

4. Run tests 
```bash
pytest
```

# Section Yohanes (Temporary)

## Data Gateway

This will spin up a data gateway, data can be extracted from redis at port 6379 with key `spot:<subscribition_channel>` e.g. (`spot:btcusdt@aggTrade`). Some data is real-time but expected refresh rate around 10ms.

How-to :

1. Up redis
```docker-compose up redis -d
``` 

2. Up data-gateway
```docker-compose up data-gateway -d
```

Env setup follow `.env.example` but please change to `.env`

## Portfolio Manager (WIP)

# Testing of Functions on Binance Testnet 
https://www.binance.com/en/support/faq/detail/ab78f9a1b8824cf0a106b4229c76496d 

python-binance documentation
https://python-binance.readthedocs.io/en/latest/


## License 
This project is intended for educational and research purposes only. 
