import tempfile
import unittest

from balancer_tracker import BalancerTracker
from data_store import PoolDataStore


class TokenExportTest(unittest.TestCase):
    def setUp(self):
        self.store = PoolDataStore(tempfile.mkdtemp())

    def test_pool_tokens_are_self_contained_and_addresses_are_lowercase(self):
        raw_pool = {
            "id": "pool-id",
            "address": "0xpool",
            "name": "msUSD-USDC",
            "dynamicData": {"totalLiquidity": "1000", "aprItems": []},
            "poolTokens": [
                {
                    "address": "0xABCDEF",
                    "symbol": "msUSD",
                    "decimals": 18,
                    "balance": "100",
                    "balanceUSD": "990",
                },
                {
                    "address": "0x123456",
                    "symbol": "USDC",
                    "decimals": 6,
                    "balance": "10",
                    "balanceUSD": "10",
                },
            ],
        }
        pool = BalancerTracker(enable_merkl=False)._parse_pool(
            raw_pool, "ethereum", check_merkl=False
        )

        exported = self.store._pool_to_json(pool, "test")["tokens"]

        self.assertEqual(
            exported,
            [
                {
                    "symbol": "msUSD",
                    "address": "0xabcdef",
                    "decimals": 18,
                    "ratio": 0.99,
                    "amount": 100.0,
                    "price": 9.9,
                },
                {
                    "symbol": "USDC",
                    "address": "0x123456",
                    "decimals": 6,
                    "ratio": 0.01,
                    "amount": 10.0,
                    "price": 1.0,
                },
            ],
        )

    def test_loader_accepts_new_and_legacy_token_shapes(self):
        base = {
            "name": "pool",
            "chain": "ethereum",
            "address": "0xpool",
            "pool_id": "pool-id",
            "data": {"bal_rewards": {}},
        }
        new = dict(base, tokens=[{
            "symbol": "USDC", "address": "0x123", "decimals": 6,
            "ratio": 1.0, "amount": 5, "price": 1,
        }])
        legacy = dict(base, tokens={
            "coins": ["USDC"], "ratios": ["USDC: 100.0%"],
            "amounts": [5], "prices": [1],
        })

        new_pool = self.store._json_to_pool(new)
        legacy_pool = self.store._json_to_pool(legacy)

        self.assertEqual(new_pool.coin_addresses, ["0x123"])
        self.assertEqual(new_pool.coin_decimals, [6])
        self.assertEqual(legacy_pool.coins, ["USDC"])
        self.assertEqual(legacy_pool.coin_addresses, [])


if __name__ == "__main__":
    unittest.main()
