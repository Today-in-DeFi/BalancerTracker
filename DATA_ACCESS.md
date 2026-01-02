# BalancerTracker Data Access

Balancer pool and Aura Finance yield data, updated on demand.

## Quick Links

**Local Paths:**
```
/home/danger/BalancerTracker/data/balancer_pools_latest.json   # Current snapshot
/home/danger/BalancerTracker/data/balancer_pools_history.json  # Time-series history
```

---

## Data Structure

### Latest Snapshot (`balancer_pools_latest.json`)

Contains the most recent pool data with full details.

```json
{
  "version": "1.0",
  "metadata": {
    "generated_at": "2025-12-13T08:56:36Z",
    "source": "BalancerTracker",
    "total_pools": 1,
    "chains": ["ethereum"],
    "has_aura": true
  },
  "pools": [...]
}
```

### Pool Object

```json
{
  "id": "ethereum_balancer_aave_lido_weth_wsteth",
  "name": "Balancer Aave Lido wETH-wstETH",
  "chain": "ethereum",
  "address": "0xc4ce391d82d164c166df9c8336ddf84206b2f812",
  "pool_id": "0xc4ce391d82d164c166df9c8336ddf84206b2f812",
  "data": {
    "tvl": 604606.37,
    "tvl_formatted": "$604.61K",
    "base_apy": 2.2646,
    "bal_rewards": {
      "min": 0.9528,
      "max": 3.3446
    },
    "other_rewards": [
      {"token": "waEthLidoWETH APR", "apy": 0.5662},
      {"token": "waEthLidowstETH APR", "apy": 1.2352}
    ],
    "total_apy": 5.0188
  },
  "tokens": {
    "coins": ["waEthLidoWETH", "waEthLidowstETH"],
    "ratios": ["waEthLidoWETH: 50.0%", "waEthLidowstETH: 50.0%"],
    "amounts": [87.682437, 84.72225],
    "prices": [0.0, 0.0]
  },
  "aura": {
    "apy": 8.7406,
    "tvl": 367588.4,
    "boost": 2.5,
    "staking_contract": "0xcf370c3279452143f68e350b824714b49593a334"
  }
}
```

### History File (`balancer_pools_history.json`)

Time-series data for tracking changes over time.

```json
{
  "version": "1.0",
  "last_updated": "2025-12-13T08:56:36Z",
  "pools": {
    "ethereum_balancer_aave_lido_weth_wsteth": {
      "metadata": {
        "name": "Balancer Aave Lido wETH-wstETH",
        "chain": "ethereum",
        "address": "0xc4ce391d82d164c166df9c8336ddf84206b2f812",
        "pool_id": "0xc4ce391d82d164c166df9c8336ddf84206b2f812"
      },
      "snapshots": [
        {
          "timestamp": "2025-12-13T08:56:36Z",
          "tvl": 604606.37,
          "base_apy": 2.2646,
          "bal_rewards_min": 0.9528,
          "bal_rewards_max": 3.3446,
          "total_apy": 5.0188,
          "aura_apy": 8.7406,
          "aura_tvl": 367588.4
        }
      ]
    }
  }
}
```

---

## Field Descriptions

### APY Fields

| Field | Description |
|-------|-------------|
| `base_apy` | Swap fee APY (what LPs earn from trading fees) |
| `bal_rewards.min` | BAL reward APY without veBAL boost |
| `bal_rewards.max` | BAL reward APY with max veBAL boost (2.5x) |
| `other_rewards` | Additional yield sources (e.g., wstETH staking yield) |
| `total_apy` | **Min APY** = base + bal_min + other (no boost) |
| `aura.apy` | **Aura APY** = base + bal_max + AURA rewards + other |

### Aura Fields

| Field | Description |
|-------|-------------|
| `aura.apy` | Total APY when staking via Aura Finance |
| `aura.tvl` | Amount staked in Aura (USD) |
| `aura.boost` | veBAL boost multiplier (typically 2.5x max) |
| `aura.staking_contract` | Aura reward pool contract address (for deposits/withdrawals) |

**Note:** `aura` is `null` if the pool is not available on Aura Finance.

### Contract Addresses

Each pool has two key addresses for on-chain interactions:

| Field | Description | Use Case |
|-------|-------------|----------|
| `address` | Balancer pool contract | Add/remove liquidity directly on Balancer |
| `aura.staking_contract` | Aura reward pool (BaseRewardPool) | Deposit BPT to earn boosted rewards on Aura |

**Workflow:**
1. Deposit tokens to Balancer pool (`address`) → receive BPT tokens
2. Stake BPT tokens in Aura (`aura.staking_contract`) → earn boosted BAL + AURA rewards

---

## Usage Examples

### Python

#### Load Latest Data
```python
import json

with open('/home/danger/BalancerTracker/data/balancer_pools_latest.json') as f:
    data = json.load(f)

print(f"Last updated: {data['metadata']['generated_at']}")
print(f"Total pools: {data['metadata']['total_pools']}")

for pool in data['pools']:
    print(f"\n{pool['name']}:")
    print(f"  TVL: {pool['data']['tvl_formatted']}")
    print(f"  Min APY (Balancer): {pool['data']['total_apy']:.2f}%")
    if pool['aura']:
        print(f"  Aura APY: {pool['aura']['apy']:.2f}%")
```

#### Get Aura-Enabled Pools
```python
import json

with open('/home/danger/BalancerTracker/data/balancer_pools_latest.json') as f:
    data = json.load(f)

aura_pools = [p for p in data['pools'] if p['aura'] is not None]

for pool in aura_pools:
    print(f"{pool['name']}: Aura APY {pool['aura']['apy']:.2f}%")
```

#### Get Contract Addresses
```python
import json

with open('/home/danger/BalancerTracker/data/balancer_pools_latest.json') as f:
    data = json.load(f)

for pool in data['pools']:
    print(f"{pool['name']}:")
    print(f"  Balancer Pool:        {pool['address']}")
    if pool['aura']:
        print(f"  Aura Staking Contract: {pool['aura']['staking_contract']}")
    else:
        print(f"  Aura: Not available")
```

#### Get Pool by Address
```python
import json

def get_pool_by_address(address):
    with open('/home/danger/BalancerTracker/data/balancer_pools_latest.json') as f:
        data = json.load(f)

    address_lower = address.lower()
    for pool in data['pools']:
        if pool['address'].lower() == address_lower:
            return pool
    return None

pool = get_pool_by_address('0xc4ce391d82d164c166df9c8336ddf84206b2f812')
if pool:
    print(f"Found: {pool['name']}")
    print(f"TVL: ${pool['data']['tvl']:,.2f}")
```

#### Read History for a Pool
```python
import json

with open('/home/danger/BalancerTracker/data/balancer_pools_history.json') as f:
    history = json.load(f)

pool_key = 'ethereum_balancer_aave_lido_weth_wsteth'
if pool_key in history['pools']:
    pool_history = history['pools'][pool_key]
    print(f"Pool: {pool_history['metadata']['name']}")
    print(f"Snapshots: {len(pool_history['snapshots'])}")

    for snapshot in pool_history['snapshots'][-5:]:  # Last 5
        print(f"  {snapshot['timestamp']}: TVL=${snapshot['tvl']:,.0f}, APY={snapshot['total_apy']:.2f}%")
```

### Shell (jq)

#### Get All Pool Names
```bash
cat /home/danger/BalancerTracker/data/balancer_pools_latest.json | jq -r '.pools[].name'
```

#### Get Pool TVL and APYs
```bash
cat /home/danger/BalancerTracker/data/balancer_pools_latest.json | \
  jq -r '.pools[] | "\(.name): TVL=\(.data.tvl_formatted), MinAPY=\(.data.total_apy)%, AuraAPY=\(.aura.apy // "N/A")%"'
```

#### Check Last Update Time
```bash
cat /home/danger/BalancerTracker/data/balancer_pools_latest.json | jq -r '.metadata.generated_at'
```

#### Get Contract Addresses
```bash
cat /home/danger/BalancerTracker/data/balancer_pools_latest.json | \
  jq -r '.pools[] | "\(.name)\n  Balancer: \(.address)\n  Aura:     \(.aura.staking_contract // "N/A")"'
```

---

## Refreshing Data

To update the JSON files with fresh data:

```bash
cd /home/danger/BalancerTracker

# Fetch and save to JSON only
python3 balancer_tracker.py

# Fetch + export to Google Sheets
python3 balancer_tracker.py --export-sheets
```

---

## Pool Configuration

Pools to track are configured in `pools.json`:

```json
{
  "settings": {
    "aura_enabled": true
  },
  "pools": [
    {
      "chain": "ethereum",
      "pool": "0xc4ce391d82d164c166df9c8336ddf84206b2f812",
      "asset_type": "ETH",
      "comment": "wstETH/WETH Aave Lido",
      "aura_enabled": true
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `chain` | Blockchain (ethereum, arbitrum, polygon, etc.) |
| `pool` | Pool contract address |
| `asset_type` | ETH or USD (for Google Sheets organization) |
| `aura_enabled` | Whether to fetch Aura data for this pool |
| `comment` | Human-readable description |

---

## Data Sources

| Data | Source |
|------|--------|
| Pool TVL, APYs, Tokens | Balancer GraphQL API (`api-v3.balancer.fi`) |
| BAL Reward Rates | Balancer API (`aprItems`) |
| Aura Pool Data | Aura Subgraph (`api.subgraph.ormilabs.com`) |
| AURA Token Price | CoinGecko API |

---

## Related Files

```
BalancerTracker/
├── balancer_tracker.py      # Main tracker script
├── data_store.py            # JSON storage layer
├── pools.json               # Pool configuration
├── Google Credentials.json  # For Sheets export
└── data/
    ├── balancer_pools_latest.json   # Current snapshot
    └── balancer_pools_history.json  # Time-series
```
