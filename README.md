# Polymarket Trading UI

Local web interface for browsing Polymarket markets, viewing positions, and placing BUY market orders via the CLOB API.

## Prerequisites

- Python 3.10+
- A Polymarket account with a funded deposit wallet on Polygon (chain ID 137)
- Your wallet private key (EOA that controls the Polymarket account)

## Setup

1. **Clone the repo**

   ```bash
   git clone <repo-url>
   cd polymarket
   ```

2. **Create a virtual environment and install dependencies**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and fill in at minimum:

   | Variable | Required | Description |
   |----------|----------|-------------|
   | `PRIVATE_KEY` | Yes | Your EOA private key (0x-prefixed, 64 hex chars) |
   | `DEPOSIT_WALLET_ADDRESS` | Yes | Your Polymarket deposit wallet address |
   | `SIGNATURE_TYPE` | No | `0` = EOA (default), `1` = email/Magic proxy, `2` = browser proxy |
   | `POLYMARKET_PROXY_ADDRESS` | If sig type 1/2 | Your proxy wallet address |
   | `TRADING_ENABLED` | No | Set to `1` to allow real order submission (off by default) |

   API credentials (`CLOB_API_KEY`, `CLOB_API_SECRET`, `CLOB_API_PASSPHRASE`) are auto-derived from `PRIVATE_KEY` if left blank.

## Run

```bash
source .venv/bin/activate
python app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

To change the port:

```bash
PORT=8080 python app.py
```

### Enable live trading

By default, order submission is disabled (preview-only mode). To enable:

```bash
TRADING_ENABLED=1 python app.py
```

## Features

- **Browse markets** — search and paginate Polymarket events
- **View positions** — see your current holdings
- **Open orders** — list active orders
- **Wallet balance** — check collateral (pUSD/USDC)
- **Order preview** — simulate market orders before submitting
- **Place orders** — submit BUY market orders (FOK) when trading is enabled
- **Copy trading profiles** — track and mirror other wallets' positions

## Project Structure

```
app.py              Flask web server + API routes
polyclient.py       Polymarket CLOB/Gamma API client
place_market_order.py   Standalone order placement script
get_orders.py       Standalone order retrieval script
static/index.html   Frontend SPA
profiles.json       Saved copy-trading profiles
.env.example        Environment variable template
```

## Security Notes

- The server binds to **localhost only** — do not expose to a network.
- **Never commit `.env`** — it contains your private key.
- Trading is disabled by default; requires explicit `TRADING_ENABLED=1`.
