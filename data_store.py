"""
Data Store for BalancerTracker
JSON-based storage layer - the source of truth for pool data
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class PoolData:
    """Data structure for Balancer pool information"""
    name: str
    chain: str
    address: str
    pool_id: str  # Balancer pool ID (different from address)
    tvl: float
    base_apy: float  # Swap fee APY
    bal_rewards_apy: List[float]  # [min, max] based on boost
    other_rewards: List[Dict[str, Any]]
    total_apy: float
    coins: List[str]
    coin_ratios: List[str]
    coin_amounts: List[float] = field(default_factory=list)
    coin_prices: List[float] = field(default_factory=list)
    # Aura Finance fields
    aura_apy: Optional[float] = None
    aura_tvl: Optional[float] = None
    aura_boost: Optional[float] = None
    aura_staking_contract: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PoolData':
        """Create PoolData from dictionary"""
        return cls(**data)


class PoolDataStore:
    """
    JSON-based storage for Balancer pool data.

    This is the source of truth - all pool data flows through here.
    """

    def __init__(self, data_dir: str = "data"):
        """
        Initialize the data store.

        Args:
            data_dir: Directory for JSON files (default: "data")
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        # File paths
        self.latest_file = os.path.join(data_dir, "balancer_pools_latest.json")
        self.history_file = os.path.join(data_dir, "balancer_pools_history.json")

    def save(self, pool_data_list: List[PoolData]) -> str:
        """
        Save current pool data snapshot.

        Args:
            pool_data_list: List of PoolData objects

        Returns:
            Path to saved file
        """
        if not pool_data_list:
            print("No pool data to save")
            return ""

        timestamp = datetime.utcnow()

        data = {
            "version": "1.0",
            "metadata": {
                "generated_at": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source": "BalancerTracker",
                "total_pools": len(pool_data_list),
                "chains": sorted(set(p.chain for p in pool_data_list)),
                "has_aura": any(p.aura_apy is not None for p in pool_data_list)
            },
            "pools": [self._pool_to_json(p) for p in pool_data_list]
        }

        with open(self.latest_file, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Saved {len(pool_data_list)} pools to {self.latest_file}")
        return self.latest_file

    def load(self) -> List[PoolData]:
        """
        Load latest pool data from JSON.

        Returns:
            List of PoolData objects
        """
        if not os.path.exists(self.latest_file):
            print(f"No data file found at {self.latest_file}")
            return []

        try:
            with open(self.latest_file, "r") as f:
                data = json.load(f)

            pools = []
            for pool_json in data.get("pools", []):
                pool = self._json_to_pool(pool_json)
                if pool:
                    pools.append(pool)

            print(f"Loaded {len(pools)} pools from {self.latest_file}")
            return pools

        except json.JSONDecodeError as e:
            print(f"Error reading JSON: {e}")
            return []

    def append_history(self, pool_data_list: List[PoolData], max_snapshots: int = None) -> str:
        """
        Append current data to history file for time-series tracking.

        Args:
            pool_data_list: List of PoolData objects
            max_snapshots: Optional limit on snapshots per pool

        Returns:
            Path to history file
        """
        if not pool_data_list:
            return ""

        timestamp = datetime.utcnow()
        timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Load existing history or create new
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    history = json.load(f)
            except json.JSONDecodeError:
                history = self._empty_history()
        else:
            history = self._empty_history()

        # Update timestamp
        history["last_updated"] = timestamp_str

        # Append snapshot for each pool
        for pool in pool_data_list:
            pool_key = self._generate_pool_key(pool)

            if pool_key not in history["pools"]:
                history["pools"][pool_key] = {
                    "metadata": {
                        "name": pool.name,
                        "chain": pool.chain,
                        "address": pool.address,
                        "pool_id": pool.pool_id
                    },
                    "snapshots": []
                }

            snapshot = {
                "timestamp": timestamp_str,
                "tvl": round(pool.tvl, 2),
                "base_apy": round(pool.base_apy, 4),
                "bal_rewards_min": round(pool.bal_rewards_apy[0], 4) if pool.bal_rewards_apy else 0,
                "bal_rewards_max": round(pool.bal_rewards_apy[1], 4) if len(pool.bal_rewards_apy) > 1 else 0,
                "total_apy": round(pool.total_apy, 4)
            }

            # Add Aura data if present
            if pool.aura_apy is not None:
                snapshot["aura_apy"] = round(pool.aura_apy, 4)
            if pool.aura_tvl is not None:
                snapshot["aura_tvl"] = round(pool.aura_tvl, 2)

            history["pools"][pool_key]["snapshots"].append(snapshot)

            # Trim old snapshots if limit set
            if max_snapshots:
                snapshots = history["pools"][pool_key]["snapshots"]
                if len(snapshots) > max_snapshots:
                    history["pools"][pool_key]["snapshots"] = snapshots[-max_snapshots:]

        # Save updated history
        with open(self.history_file, "w") as f:
            json.dump(history, f, indent=2)

        total_snapshots = sum(len(p["snapshots"]) for p in history["pools"].values())
        print(f"History updated: {len(pool_data_list)} pools, {total_snapshots} total snapshots")

        return self.history_file

    def get_history(self, pool_key: str = None, days: int = None) -> Dict[str, Any]:
        """
        Get historical data.

        Args:
            pool_key: Specific pool key, or None for all pools
            days: Limit to last N days, or None for all

        Returns:
            History data dictionary
        """
        if not os.path.exists(self.history_file):
            return {}

        try:
            with open(self.history_file, "r") as f:
                history = json.load(f)

            if pool_key:
                pool_history = history.get("pools", {}).get(pool_key, {})
                if days:
                    pool_history = self._filter_by_days(pool_history, days)
                return pool_history

            if days:
                # Filter all pools by days
                filtered = {"pools": {}}
                for key, pool_data in history.get("pools", {}).items():
                    filtered["pools"][key] = self._filter_by_days(pool_data, days)
                return filtered

            return history

        except json.JSONDecodeError:
            return {}

    def save_archive(self, pool_data_list: List[PoolData]) -> str:
        """
        Save dated archive file.

        Args:
            pool_data_list: List of PoolData objects

        Returns:
            Path to archive file
        """
        if not pool_data_list:
            return ""

        date_str = datetime.utcnow().strftime("%Y%m%d")
        archive_file = os.path.join(self.data_dir, f"balancer_pools_{date_str}.json")

        timestamp = datetime.utcnow()

        data = {
            "version": "1.0",
            "metadata": {
                "generated_at": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source": "BalancerTracker",
                "total_pools": len(pool_data_list),
                "chains": sorted(set(p.chain for p in pool_data_list))
            },
            "pools": [self._pool_to_json(p) for p in pool_data_list]
        }

        with open(archive_file, "w") as f:
            json.dump(data, f, indent=2)

        print(f"Archive saved to {archive_file}")
        return archive_file

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata from latest file without loading all pools"""
        if not os.path.exists(self.latest_file):
            return {}

        try:
            with open(self.latest_file, "r") as f:
                data = json.load(f)
            return data.get("metadata", {})
        except json.JSONDecodeError:
            return {}

    def _pool_to_json(self, pool: PoolData) -> Dict[str, Any]:
        """Convert PoolData to JSON-serializable dict with structure"""
        return {
            "id": self._generate_pool_key(pool),
            "name": pool.name,
            "chain": pool.chain,
            "address": pool.address,
            "pool_id": pool.pool_id,
            "data": {
                "tvl": round(pool.tvl, 2),
                "tvl_formatted": self._format_currency(pool.tvl),
                "base_apy": round(pool.base_apy, 4),
                "bal_rewards": {
                    "min": round(pool.bal_rewards_apy[0], 4) if pool.bal_rewards_apy else 0,
                    "max": round(pool.bal_rewards_apy[1], 4) if len(pool.bal_rewards_apy) > 1 else 0
                },
                "other_rewards": pool.other_rewards,
                "total_apy": round(pool.total_apy, 4)
            },
            "tokens": {
                "coins": pool.coins,
                "ratios": pool.coin_ratios,
                "amounts": [round(a, 6) for a in pool.coin_amounts],
                "prices": [round(p, 4) for p in pool.coin_prices]
            },
            "aura": {
                "apy": round(pool.aura_apy, 4) if pool.aura_apy is not None else None,
                "tvl": round(pool.aura_tvl, 2) if pool.aura_tvl is not None else None,
                "boost": round(pool.aura_boost, 2) if pool.aura_boost is not None else None,
                "staking_contract": pool.aura_staking_contract
            } if pool.aura_apy is not None else None
        }

    def _json_to_pool(self, data: Dict[str, Any]) -> Optional[PoolData]:
        """Convert JSON dict back to PoolData"""
        try:
            pool_data = data.get("data", {})
            tokens = data.get("tokens", {})
            aura = data.get("aura") or {}

            bal_rewards = pool_data.get("bal_rewards", {})

            return PoolData(
                name=data.get("name", "Unknown"),
                chain=data.get("chain", "ethereum"),
                address=data.get("address", ""),
                pool_id=data.get("pool_id", ""),
                tvl=pool_data.get("tvl", 0),
                base_apy=pool_data.get("base_apy", 0),
                bal_rewards_apy=[bal_rewards.get("min", 0), bal_rewards.get("max", 0)],
                other_rewards=pool_data.get("other_rewards", []),
                total_apy=pool_data.get("total_apy", 0),
                coins=tokens.get("coins", []),
                coin_ratios=tokens.get("ratios", []),
                coin_amounts=tokens.get("amounts", []),
                coin_prices=tokens.get("prices", []),
                aura_apy=aura.get("apy"),
                aura_tvl=aura.get("tvl"),
                aura_boost=aura.get("boost"),
                aura_staking_contract=aura.get("staking_contract")
            )
        except Exception as e:
            print(f"Error parsing pool data: {e}")
            return None

    def _generate_pool_key(self, pool: PoolData) -> str:
        """Generate unique key for a pool"""
        import re
        name = pool.name.lower()
        name = re.sub(r'[^a-z0-9]+', '_', name).strip('_')
        return f"{pool.chain}_{name}"

    def _format_currency(self, amount: float) -> str:
        """Format currency with suffixes"""
        if amount >= 1_000_000_000:
            return f"${amount/1_000_000_000:.2f}B"
        elif amount >= 1_000_000:
            return f"${amount/1_000_000:.2f}M"
        elif amount >= 1_000:
            return f"${amount/1_000:.2f}K"
        else:
            return f"${amount:.2f}"

    def _empty_history(self) -> Dict[str, Any]:
        """Create empty history structure"""
        return {
            "version": "1.0",
            "last_updated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pools": {}
        }

    def _filter_by_days(self, pool_data: Dict, days: int) -> Dict:
        """Filter snapshots to last N days"""
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)

        if "snapshots" not in pool_data:
            return pool_data

        filtered_snapshots = []
        for snapshot in pool_data.get("snapshots", []):
            try:
                ts = datetime.strptime(snapshot["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
                if ts >= cutoff:
                    filtered_snapshots.append(snapshot)
            except (KeyError, ValueError):
                continue

        return {
            **pool_data,
            "snapshots": filtered_snapshots
        }
