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
    # Wrapper family: which protocol's wrapped tokens this pool holds.
    # "aave" (waMon*/waEth*/waBas*) vs "neverland" (wn*) etc. Two pools can hold the
    # same underlying assets with different wrappers and carry ~2x different yields,
    # so consumers must join on this + address, never on display name or tickers.
    wrapper: Optional[str] = None           # single family, "mixed", or None if unwrapped
    wrappers: List[str] = field(default_factory=list)  # every family detected, sorted
    # Merkl cross-check: Balancer and Merkl publish different numbers for the same
    # campaign. total_apy is built from Balancer's aprItems; Merkl's own figure is
    # carried alongside so consumers can see the gap instead of picking blind.
    merkl_apr_balancer: Optional[float] = None
    merkl_apr_merkl: Optional[float] = None
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
        keys = self._generate_pool_keys(pool_data_list)

        data = {
            "version": "1.0",
            "metadata": {
                "generated_at": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source": "BalancerTracker",
                "total_pools": len(pool_data_list),
                "chains": sorted(set(p.chain for p in pool_data_list)),
                "has_aura": any(p.aura_apy is not None for p in pool_data_list)
            },
            "pools": [self._pool_to_json(p, keys[self._generate_pool_uid(p)])
                      for p in pool_data_list]
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

        keys = self._generate_pool_keys(pool_data_list)

        # Append snapshot for each pool
        for pool in pool_data_list:
            pool_key = keys[self._generate_pool_uid(pool)]

            if pool_key not in history["pools"]:
                history["pools"][pool_key] = {
                    "metadata": {
                        "uid": self._generate_pool_uid(pool),
                        "name": pool.name,
                        "chain": pool.chain,
                        "address": pool.address,
                        "pool_id": pool.pool_id,
                        "wrapper": pool.wrapper
                    },
                    "snapshots": []
                }
            else:
                # Backfill fields added after this pool was first recorded
                meta = history["pools"][pool_key].setdefault("metadata", {})
                meta.setdefault("uid", self._generate_pool_uid(pool))
                meta["wrapper"] = pool.wrapper

            snapshot = {
                "timestamp": timestamp_str,
                "tvl": round(pool.tvl, 2),
                "base_apy": round(pool.base_apy, 4),
                "bal_rewards_min": round(pool.bal_rewards_apy[0], 4) if pool.bal_rewards_apy else 0,
                "bal_rewards_max": round(pool.bal_rewards_apy[1], 4) if len(pool.bal_rewards_apy) > 1 else 0,
                "total_apy": round(pool.total_apy, 4)
            }

            # Merkl's own figure, for tracking the Balancer/Merkl gap over time
            if pool.merkl_apr_balancer is not None:
                snapshot["merkl_apr_balancer"] = round(pool.merkl_apr_balancer, 4)
            if pool.merkl_apr_merkl is not None:
                snapshot["merkl_apr_merkl"] = round(pool.merkl_apr_merkl, 4)

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
        keys = self._generate_pool_keys(pool_data_list)

        data = {
            "version": "1.0",
            "metadata": {
                "generated_at": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source": "BalancerTracker",
                "total_pools": len(pool_data_list),
                "chains": sorted(set(p.chain for p in pool_data_list))
            },
            "pools": [self._pool_to_json(p, keys[self._generate_pool_uid(p)])
                      for p in pool_data_list]
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

    def _pool_to_json(self, pool: PoolData, pool_key: str = None) -> Dict[str, Any]:
        """Convert PoolData to JSON-serializable dict with structure"""
        result = {
            "id": pool_key or self._generate_pool_key(pool),
            # Canonical join key: chain + full address. Never collides, never changes.
            # Prefer this over "id" (derived from the display name) when matching pools.
            "uid": self._generate_pool_uid(pool),
            "name": pool.name,
            "chain": pool.chain,
            "address": pool.address,
            "pool_id": pool.pool_id,
            "wrapper": pool.wrapper,
            "wrappers": pool.wrappers,
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
            "merkl": self._merkl_to_json(pool),
            # Flat aura_apy field for FarmTracker compatibility
            "aura_apy": round(pool.aura_apy, 4) if pool.aura_apy is not None else None,
            "aura": {
                "apy": round(pool.aura_apy, 4) if pool.aura_apy is not None else None,
                "tvl": round(pool.aura_tvl, 2) if pool.aura_tvl is not None else None,
                "boost": round(pool.aura_boost, 2) if pool.aura_boost is not None else None,
                "staking_contract": pool.aura_staking_contract
            } if pool.aura_apy is not None else None
        }
        return result

    def _json_to_pool(self, data: Dict[str, Any]) -> Optional[PoolData]:
        """Convert JSON dict back to PoolData"""
        try:
            pool_data = data.get("data", {})
            tokens = data.get("tokens", {})
            aura = data.get("aura") or {}
            merkl = data.get("merkl") or {}

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
                wrapper=data.get("wrapper"),
                wrappers=data.get("wrappers", []),
                merkl_apr_balancer=merkl.get("apr_balancer"),
                merkl_apr_merkl=merkl.get("apr_merkl"),
                aura_apy=aura.get("apy"),
                aura_tvl=aura.get("tvl"),
                aura_boost=aura.get("boost"),
                aura_staking_contract=aura.get("staking_contract")
            )
        except Exception as e:
            print(f"Error parsing pool data: {e}")
            return None

    def _merkl_to_json(self, pool: PoolData) -> Optional[Dict[str, Any]]:
        """
        Merkl reward APR as reported by both sources.

        Balancer and Merkl regularly disagree about the same campaign (2-3pp gaps are
        common on the dominant APR component). `total_apy` is composed from Balancer's
        aprItems, so `source` is always "balancer" - `apr_merkl` is a cross-check, not
        an alternative total. `delta_pp` is positive when Balancer publishes the higher
        number. Returns None for pools with no Merkl campaign.
        """
        if pool.merkl_apr_balancer is None and pool.merkl_apr_merkl is None:
            return None

        delta = None
        if pool.merkl_apr_balancer is not None and pool.merkl_apr_merkl is not None:
            delta = round(pool.merkl_apr_balancer - pool.merkl_apr_merkl, 4)

        return {
            "source": "balancer",
            "apr_published": round(pool.merkl_apr_balancer, 4) if pool.merkl_apr_balancer is not None else None,
            "apr_balancer": round(pool.merkl_apr_balancer, 4) if pool.merkl_apr_balancer is not None else None,
            "apr_merkl": round(pool.merkl_apr_merkl, 4) if pool.merkl_apr_merkl is not None else None,
            "delta_pp": delta
        }

    def _generate_pool_uid(self, pool: PoolData) -> str:
        """
        Canonical, collision-free identifier: chain + full pool address.

        Display names are not unique - Monad alone has several pools whose names and
        ticker sets differ only by a wrapper prefix (wnUSDT0 vs waMonUSDT0). Consumers
        should join on this.
        """
        return f"{pool.chain}_{pool.address.lower()}"

    def _generate_pool_key(self, pool: PoolData) -> str:
        """
        Generate a human-readable key for a pool (chain + slugified name).

        Not guaranteed unique - use _generate_pool_keys() when handling a batch so
        same-name pools get disambiguated instead of silently overwriting each other.
        """
        import re
        name = pool.name.lower()
        name = re.sub(r'[^a-z0-9]+', '_', name).strip('_')
        return f"{pool.chain}_{name}"

    def _generate_pool_keys(self, pool_data_list: List[PoolData]) -> Dict[str, str]:
        """
        Map each pool's uid -> display key, disambiguating name collisions.

        Two Balancer pools on one chain can share a name ("Aave 3-pool" is not a
        unique string). Left alone they would collapse onto one key and merge their
        history snapshots. When that happens every colliding pool gets an address
        suffix, so the result depends only on the set of pools, not on their order.

        Args:
            pool_data_list: List of PoolData objects

        Returns:
            Dict of uid -> key
        """
        by_key: Dict[str, List[PoolData]] = {}
        for pool in pool_data_list:
            by_key.setdefault(self._generate_pool_key(pool), []).append(pool)

        keys: Dict[str, str] = {}
        for key, pools in by_key.items():
            # Distinct addresses only - the same pool listed twice is not a collision
            addresses = {p.address.lower() for p in pools}
            for pool in pools:
                if len(addresses) > 1:
                    suffix = pool.address.lower().replace("0x", "")[:6]
                    keys[self._generate_pool_uid(pool)] = f"{key}_{suffix}"
                else:
                    keys[self._generate_pool_uid(pool)] = key

            if len(addresses) > 1:
                print(f"Warning: {len(addresses)} pools share the key '{key}' "
                      f"({', '.join(sorted(addresses))}); disambiguating by address")

        return keys

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
