#!/usr/bin/env python3
"""Check if a Balancer pool is tracked in pools.json."""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Check if a Balancer pool is tracked")
    parser.add_argument("--pool", required=True, help="Pool contract address (0x...)")
    parser.add_argument("--chain", required=True, help="Chain name (e.g. ethereum, base, monad)")
    args = parser.parse_args()

    pools_path = Path(__file__).parent.parent / "pools.json"
    try:
        with open(pools_path) as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Error: {pools_path} not found", file=sys.stderr)
        sys.exit(1)

    pool_addr = args.pool.lower()
    chain = args.chain.lower()

    for entry in config.get("pools", []):
        if entry["pool"].lower() == pool_addr and entry.get("chain", "").lower() == chain:
            result = {
                "tracked": True,
                "pool": entry["pool"],
                "chain": entry.get("chain"),
                "comment": entry.get("comment"),
                "asset_type": entry.get("asset_type"),
                "aura_enabled": entry.get("aura_enabled", False),
                "details": f"Found in pools.json: {entry.get('comment', '')}",
                "add_entry": None,
                "add_command": None,
            }
            json.dump(result, sys.stdout, indent=2)
            print()
            sys.exit(0)

    result = {
        "tracked": False,
        "pool": args.pool,
        "chain": args.chain,
        "details": "Pool not found in pools.json",
        "add_entry": {
            "chain": args.chain,
            "pool": args.pool,
            "asset_type": "FILL_IN (USD|ETH)",
            "comment": "FILL_IN (e.g., tokenA/tokenB pool description)",
            "aura_enabled": False,
        },
        "add_command": None,
    }
    json.dump(result, sys.stdout, indent=2)
    print()
    sys.exit(0)


if __name__ == "__main__":
    main()
