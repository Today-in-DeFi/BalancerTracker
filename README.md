# BalancerTracker

Track Balancer pool metrics (TVL, APY, composition) with Aura Finance yield booster integration.

## Features

- Fetch Balancer pool data (TVL, fees, APY)
- Aura Finance integration for boosted yields
- Export to Google Sheets
- JSON export for programmatic access
- Multi-chain support (Ethereum, Arbitrum, etc.)

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure pools in `pools.json`

3. (Optional) Add Google credentials for Sheets export

## Usage

```bash
# Basic run
python balancer_tracker.py

# Disable JSON export
python balancer_tracker.py --no-json

# Export to Google Sheets
python balancer_tracker.py --credentials "Google Credentials.json"

# Check if a pool is already tracked
python3 scripts/check_tracked.py --pool 0xc4ce...b812 --chain ethereum
```

## Configuration

Edit `pools.json` to configure tracked pools. Set `wrapper` (`aave`, `neverland`, ...)
on any pool that has a lookalike — chains routinely run pools over the same underlying
assets through different wrappers, and they pay materially different yields. See
`DATA_ACCESS.md` for how consumers should match pools.

```json
{
  "settings": {
    "aura_enabled": true
  },
  "pools": [
    {
      "chain": "ethereum",
      "pool": "0x...",
      "comment": "Pool description",
      "wrapper": "aave",
      "aura_enabled": true
    }
  ]
}
```
