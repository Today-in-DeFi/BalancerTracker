#!/usr/bin/env python3
"""
Balancer Pool Tracker
Fetches TVL, APY, and rewards data for Balancer pools with Aura Finance integration
"""

import requests
import json
import time
from typing import Dict, List, Optional, Union
from tabulate import tabulate
import argparse
import sys
import os
from datetime import datetime
from dotenv import load_dotenv

from data_store import PoolDataStore, PoolData

# Load environment variables
load_dotenv()


class BalancerAPI:
    """Balancer GraphQL API client"""

    BASE_URL = "https://api-v3.balancer.fi/"

    # Chain name to GraphQL enum mapping
    CHAIN_MAP = {
        'ethereum': 'MAINNET',
        'mainnet': 'MAINNET',
        'arbitrum': 'ARBITRUM',
        'polygon': 'POLYGON',
        'optimism': 'OPTIMISM',
        'base': 'BASE',
        'gnosis': 'GNOSIS',
        'avalanche': 'AVALANCHE',
        'zkevm': 'ZKEVM',
        'fraxtal': 'FRAXTAL',
        'mode': 'MODE',
        'sonic': 'SONIC',
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'BalancerTracker/1.0',
            'Content-Type': 'application/json'
        })
        self._pool_cache = {}  # Cache address -> pool ID mapping

    def _gql_chain(self, chain: str) -> str:
        """Convert chain name to GraphQL enum"""
        return self.CHAIN_MAP.get(chain.lower(), 'MAINNET')

    def _make_request(self, query: str, variables: Dict = None) -> Dict:
        """Make GraphQL request"""
        payload = {'query': query}
        if variables:
            payload['variables'] = variables

        try:
            response = self.session.post(self.BASE_URL, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()

            if 'errors' in result:
                print(f"GraphQL errors: {result['errors']}")
                return {}

            return result.get('data', {})
        except requests.exceptions.RequestException as e:
            print(f"Balancer API request failed: {e}")
            return {}

    def get_pool_by_id(self, pool_id: str, chain: str = 'ethereum') -> Optional[Dict]:
        """Get pool data by full pool ID"""
        query = """
        query GetPool($poolId: String!, $chain: GqlChain!) {
            poolGetPool(id: $poolId, chain: $chain) {
                id
                address
                name
                symbol
                type
                version
                dynamicData {
                    totalLiquidity
                    totalShares
                    fees24h
                    volume24h
                    aprItems {
                        title
                        type
                        apr
                        rewardTokenSymbol
                    }
                }
                poolTokens {
                    address
                    symbol
                    decimals
                    balance
                    weight
                    priceRate
                }
            }
        }
        """

        variables = {
            'poolId': pool_id,
            'chain': self._gql_chain(chain)
        }

        result = self._make_request(query, variables)
        return result.get('poolGetPool')

    def get_pools_by_address(self, addresses: List[str], chain: str = 'ethereum') -> List[Dict]:
        """Get pools by addresses (batch query)"""
        # First get pool list for chain to find matching addresses
        gql_chain = self._gql_chain(chain)

        query = """
        query GetPools($chain: [GqlChain!], $minTvl: Float) {
            poolGetPools(
                where: {chainIn: $chain, minTvl: $minTvl}
                first: 1000
                orderBy: totalLiquidity
                orderDirection: desc
            ) {
                id
                address
                name
                symbol
                type
                version
                dynamicData {
                    totalLiquidity
                    totalShares
                    fees24h
                    volume24h
                    aprItems {
                        title
                        type
                        apr
                        rewardTokenSymbol
                    }
                }
                poolTokens {
                    address
                    symbol
                    decimals
                    balance
                    weight
                    priceRate
                }
            }
        }
        """

        variables = {
            'chain': [gql_chain],
            'minTvl': 0  # Get all pools
        }

        result = self._make_request(query, variables)
        all_pools = result.get('poolGetPools', [])

        # Filter by requested addresses
        addresses_lower = [a.lower() for a in addresses]
        matching = []
        for pool in all_pools:
            if pool.get('address', '').lower() in addresses_lower:
                matching.append(pool)
                # Cache the mapping
                self._pool_cache[pool['address'].lower()] = pool['id']

        return matching

    def find_pool(self, identifier: str, chain: str = 'ethereum') -> Optional[Dict]:
        """
        Find pool by ID or address.

        Args:
            identifier: Full pool ID or contract address
            chain: Chain name

        Returns:
            Pool data dict or None
        """
        # Check if it looks like a full pool ID (64+ hex chars) or just an address (40 hex chars)
        clean_id = identifier.lower().replace('0x', '')

        if len(clean_id) > 42:
            # Looks like a full pool ID
            return self.get_pool_by_id(identifier, chain)
        else:
            # Looks like an address - search for it
            pools = self.get_pools_by_address([identifier], chain)
            return pools[0] if pools else None

    def get_top_pools(self, chain: str = 'ethereum', limit: int = 10, min_tvl: float = 100000) -> List[Dict]:
        """Get top pools by TVL"""
        query = """
        query GetTopPools($chain: [GqlChain!], $minTvl: Float, $first: Int) {
            poolGetPools(
                where: {chainIn: $chain, minTvl: $minTvl}
                first: $first
                orderBy: totalLiquidity
                orderDirection: desc
            ) {
                id
                address
                name
                symbol
                type
                dynamicData {
                    totalLiquidity
                    aprItems {
                        title
                        type
                        apr
                    }
                }
                poolTokens {
                    symbol
                    balance
                    weight
                }
            }
        }
        """

        variables = {
            'chain': [self._gql_chain(chain)],
            'minTvl': min_tvl,
            'first': limit
        }

        result = self._make_request(query, variables)
        return result.get('poolGetPools', [])


class AuraFinanceAPI:
    """Aura Finance subgraph API client"""

    # Subgraph endpoints per chain
    SUBGRAPH_URLS = {
        'ethereum': 'https://api.subgraph.ormilabs.com/api/public/396b336b-4ed7-469f-a8f4-468e1e26e9a8/subgraphs/aura-finance-mainnet/v0.0.1/',
        'mainnet': 'https://api.subgraph.ormilabs.com/api/public/396b336b-4ed7-469f-a8f4-468e1e26e9a8/subgraphs/aura-finance-mainnet/v0.0.1/',
        'arbitrum': 'https://api.subgraph.ormilabs.com/api/public/396b336b-4ed7-469f-a8f4-468e1e26e9a8/subgraphs/aura-finance-arbitrum/v0.0.1/',
        'optimism': 'https://api.subgraph.ormilabs.com/api/public/396b336b-4ed7-469f-a8f4-468e1e26e9a8/subgraphs/aura-finance-optimism/v0.0.1/',
        'base': 'https://api.subgraph.ormilabs.com/api/public/396b336b-4ed7-469f-a8f4-468e1e26e9a8/subgraphs/aura-finance-base/v0.0.1/',
        'polygon': 'https://api.subgraph.ormilabs.com/api/public/396b336b-4ed7-469f-a8f4-468e1e26e9a8/subgraphs/aura-finance-polygon/v0.0.1/',
        'avalanche': 'https://api.subgraph.ormilabs.com/api/public/396b336b-4ed7-469f-a8f4-468e1e26e9a8/subgraphs/aura-finance-avalanche/v0.0.1/',
    }

    # CoinGecko IDs for price fetching
    COINGECKO_IDS = {
        'AURA': 'aura-finance',
        'BAL': 'balancer',
        'GHO': 'gho',
        'USDC': 'usd-coin',
        'OP': 'optimism',
        'axlOP': 'optimism',
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'BalancerTracker/1.0',
            'Content-Type': 'application/json'
        })
        self._pools_cache = {}  # Cache: chain -> {lp_address -> pool_data}
        self._price_cache = {}  # Cache: token -> price
        self._prices_fetched = False  # Track if we've done batch fetch

    def _make_request(self, url: str, query: str, variables: Dict = None) -> Dict:
        """Make GraphQL request to Aura subgraph"""
        payload = {'query': query}
        if variables:
            payload['variables'] = variables

        try:
            response = self.session.post(url, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()

            if 'errors' in result:
                print(f"Aura GraphQL errors: {result['errors']}")
                return {}

            return result.get('data', {})
        except requests.exceptions.RequestException as e:
            print(f"Aura API request failed: {e}")
            return {}

    def fetch_all_prices(self, max_retries: int = 3) -> Dict[str, float]:
        """
        Batch fetch all known token prices from CoinGecko in a single request.
        Uses retry logic with exponential backoff to handle rate limits.

        Returns:
            Dict mapping symbol -> price in USD
        """
        if self._prices_fetched:
            return self._price_cache

        # Get unique CoinGecko IDs
        unique_ids = set(self.COINGECKO_IDS.values())
        ids_str = ','.join(unique_ids)

        url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids_str}&vs_currencies=usd"

        # Reverse mapping: coingecko_id -> [symbols]
        id_to_symbols = {}
        for symbol, cg_id in self.COINGECKO_IDS.items():
            if cg_id not in id_to_symbols:
                id_to_symbols[cg_id] = []
            id_to_symbols[cg_id].append(symbol)

        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                data = response.json()

                # Map prices back to symbols
                for cg_id, price_data in data.items():
                    price = price_data.get('usd')
                    if price and cg_id in id_to_symbols:
                        for symbol in id_to_symbols[cg_id]:
                            self._price_cache[symbol] = price

                self._prices_fetched = True
                return self._price_cache

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    # Rate limited - wait with exponential backoff
                    import time
                    wait_time = (2 ** attempt) * 2  # 2, 4, 8 seconds
                    if attempt < max_retries - 1:
                        time.sleep(wait_time)
                        continue
                print(f"CoinGecko batch price fetch failed: {e}")
                break
            except Exception as e:
                print(f"CoinGecko batch price fetch failed: {e}")
                break

        self._prices_fetched = True  # Don't retry on subsequent calls
        return self._price_cache

    def get_token_price(self, symbol: str) -> Optional[float]:
        """Get token price from cache (batch fetched from CoinGecko)"""
        # Ensure prices are fetched
        if not self._prices_fetched:
            self.fetch_all_prices()

        # Check cache with both original and uppercase
        if symbol in self._price_cache:
            return self._price_cache[symbol]
        if symbol.upper() in self._price_cache:
            return self._price_cache[symbol.upper()]

        return None

    def get_pools(self, chain: str = 'ethereum') -> Dict[str, Dict]:
        """
        Get all Aura pools for a chain, indexed by LP token address.

        Returns:
            Dict mapping lowercase LP address -> pool data
        """
        chain_lower = chain.lower()
        if chain_lower in self._pools_cache:
            return self._pools_cache[chain_lower]

        url = self.SUBGRAPH_URLS.get(chain_lower)
        if not url:
            return {}

        query = """
        {
            pools(first: 500) {
                id
                lpToken { id symbol }
                totalStaked
                rewardPool
                rewardData {
                    token { symbol decimals }
                    rewardRate
                    periodFinish
                }
            }
        }
        """

        result = self._make_request(url, query)
        pools = result.get('pools', [])

        # Index by LP token address
        indexed = {}
        for pool in pools:
            lp_address = pool.get('lpToken', {}).get('id', '').lower()
            if lp_address:
                indexed[lp_address] = pool

        self._pools_cache[chain_lower] = indexed
        return indexed

    def find_pool_by_balancer_address(self, balancer_address: str, chain: str = 'ethereum') -> Optional[Dict]:
        """Find Aura pool by Balancer pool address"""
        pools = self.get_pools(chain)
        return pools.get(balancer_address.lower())

    def calculate_aura_apr(self, aura_pool: Dict, tvl: float, bal_max_apr: float) -> Dict[str, float]:
        """
        Calculate Aura APRs from pool data.

        Args:
            aura_pool: Aura pool data from subgraph
            tvl: Pool TVL in USD (from Balancer)
            bal_max_apr: Max BAL APR from Balancer (with full boost)

        Returns:
            Dict with 'total_apr', 'bal_apr', 'aura_apr', 'extra_apr'
        """
        if not aura_pool or tvl <= 0:
            return {}

        seconds_per_year = 365 * 86400
        bal_apr = 0.0
        aura_apr = 0.0
        extra_apr = 0.0

        reward_data = aura_pool.get('rewardData', [])
        for reward in reward_data:
            token = reward.get('token', {})
            token_symbol = token.get('symbol', '')
            decimals = int(token.get('decimals', 18) or 18)
            reward_rate = float(reward.get('rewardRate', 0) or 0)

            # Skip if no rewards
            if reward_rate <= 0:
                continue

            # Get price
            token_price = self.get_token_price(token_symbol)
            
            # If price fetch fails for BAL, fallback to bal_max_apr to avoid showing 0%
            if not token_price:
                if token_symbol == 'BAL':
                    bal_apr = bal_max_apr
                continue

            # Calculate APR: (rewardRate * 365 * 86400 * price) / tvl * 100
            tokens_per_year = (reward_rate / (10 ** decimals)) * seconds_per_year
            apr = (tokens_per_year * token_price / tvl) * 100

            if token_symbol == 'BAL':
                bal_apr = apr
            elif token_symbol == 'AURA':
                aura_apr = apr
            else:
                extra_apr += apr

        # Total Aura APY
        total_apr = bal_apr + aura_apr + extra_apr

        return {
            'total_apr': total_apr,
            'bal_apr': bal_apr,
            'aura_apr': aura_apr,
            'extra_apr': extra_apr
        }

    def get_aura_tvl(self, aura_pool: Dict, bpt_price: float = 1.0) -> float:
        """
        Calculate Aura pool TVL from staked amount.

        Args:
            aura_pool: Aura pool data
            bpt_price: Price per BPT token (TVL / totalShares from Balancer)

        Returns:
            TVL in USD
        """
        if not aura_pool:
            return 0.0

        total_staked = float(aura_pool.get('totalStaked', 0) or 0)
        # totalStaked is in wei (18 decimals)
        staked_tokens = total_staked / 1e18
        return staked_tokens * bpt_price


class GoogleSheetsExporter:
    """Export pool data to Google Sheets - reads from data_store"""

    DEFAULT_SHEET_ID = '11192EotO_6hJUdhfmrO8DjyIJ3x3YADDGpChyBHKnD4'

    HEADERS = [
        'Pool Name',
        'Address',
        'Coins',
        'TVL',
        'Base APY',
        'BAL Min',
        'BAL Max',
        'Other Rewards',
        'Min APY',
        'Aura APY',
        'Aura TVL',
        'Aura Staking Contract',
        'Last Updated'
    ]

    def __init__(self, credentials_path: str = None, sheet_id: str = None):
        self.credentials_path = credentials_path or 'Google Credentials.json'
        self.sheet_id = sheet_id or self.DEFAULT_SHEET_ID
        self.client = None

    def _get_client(self):
        """Initialize Google Sheets client"""
        if self.client:
            return self.client

        try:
            from google.oauth2 import service_account
            import gspread

            SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
            creds = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=SCOPES
            )
            self.client = gspread.authorize(creds)
            return self.client
        except Exception as e:
            print(f"Failed to initialize Google Sheets client: {e}")
            return None

    def _get_sheet_name(self, chain: str, asset_type: str) -> str:
        """Generate sheet name from chain and asset type"""
        chain_title = chain.title()
        return f"{chain_title} {asset_type.upper()}"

    def _format_pool_row(self, pool: PoolData) -> List:
        """Format a pool as a row for the sheet"""
        # Format other rewards
        if pool.other_rewards:
            other_str = sum(r['apy'] for r in pool.other_rewards)
            other_formatted = f"{other_str:.2f}%"
        else:
            other_formatted = "0.00%"

        # Format coins
        coins_str = "/".join(pool.coins[:4])
        if len(pool.coins) > 4:
            coins_str += "..."

        return [
            pool.name,
            pool.address,
            coins_str,
            f"${pool.tvl:,.2f}",
            f"{pool.base_apy:.2f}%",
            f"{pool.bal_rewards_apy[0]:.2f}%" if pool.bal_rewards_apy else "0.00%",
            f"{pool.bal_rewards_apy[1]:.2f}%" if len(pool.bal_rewards_apy) > 1 else "0.00%",
            other_formatted,
            f"{pool.total_apy:.2f}%",
            f"{pool.aura_apy:.2f}%" if pool.aura_apy is not None else "",
            f"${pool.aura_tvl:,.2f}" if pool.aura_tvl else "",
            pool.aura_staking_contract if pool.aura_staking_contract else "",
            datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        ]

    def export(self, pools: List[PoolData], pools_config: List[Dict] = None) -> bool:
        """
        Export pools to Google Sheets, organized by chain and asset type.

        Args:
            pools: List of PoolData objects
            pools_config: Original config with asset_type info

        Returns:
            True if successful
        """
        client = self._get_client()
        if not client:
            return False

        try:
            spreadsheet = client.open_by_key(self.sheet_id)
        except Exception as e:
            print(f"Failed to open spreadsheet: {e}")
            return False

        # Build address -> asset_type mapping from config
        asset_map = {}
        if pools_config:
            for cfg in pools_config:
                addr = cfg.get('pool', '').lower()
                asset_type = cfg.get('asset_type', 'OTHER')
                asset_map[addr] = asset_type

        # Group pools by chain + asset_type
        grouped = {}
        for pool in pools:
            asset_type = asset_map.get(pool.address.lower(), 'OTHER')
            sheet_name = self._get_sheet_name(pool.chain, asset_type)

            if sheet_name not in grouped:
                grouped[sheet_name] = []
            grouped[sheet_name].append(pool)

        # Export each group to its sheet
        for sheet_name, sheet_pools in grouped.items():
            try:
                # Get or create worksheet
                try:
                    worksheet = spreadsheet.worksheet(sheet_name)
                except:
                    worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=100, cols=20)

                # Clear existing data
                worksheet.clear()

                # Write headers
                worksheet.update(values=[self.HEADERS], range_name='A1')

                # Write data rows
                rows = [self._format_pool_row(pool) for pool in sheet_pools]
                if rows:
                    worksheet.update(values=rows, range_name=f'A2:M{len(rows) + 1}')

                print(f"Exported {len(sheet_pools)} pools to '{sheet_name}'")

            except Exception as e:
                print(f"Failed to export to '{sheet_name}': {e}")
                continue

        return True

    def _cleanup_old_log_data(self, worksheet, days_to_keep: int = 30) -> int:
        """
        Remove log entries older than specified days.

        Args:
            worksheet: The Log worksheet to clean
            days_to_keep: Number of days of history to retain (default: 30)

        Returns:
            Number of rows deleted
        """
        from datetime import timedelta

        try:
            all_values = worksheet.get_all_values()

            if len(all_values) <= 1:
                return 0

            headers = all_values[0]
            data_rows = all_values[1:]

            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

            rows_to_keep = []
            rows_deleted = 0

            for row in data_rows:
                if not row or len(row) < 2:
                    continue

                date_str = row[0]
                time_str = row[1]
                try:
                    timestamp_str = f"{date_str} {time_str}"
                    row_timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')

                    if row_timestamp >= cutoff_date:
                        rows_to_keep.append(row)
                    else:
                        rows_deleted += 1
                except (ValueError, IndexError):
                    rows_to_keep.append(row)

            if rows_deleted > 0:
                worksheet.clear()
                new_data = [headers] + rows_to_keep
                worksheet.update(values=new_data, range_name='A1')
                print(f"Cleaned up {rows_deleted} old rows (keeping last {days_to_keep} days)")

            return rows_deleted

        except Exception as e:
            print(f"Warning: Could not cleanup old log data: {e}")
            return 0

    def export_to_log_sheet(self, pools: List[PoolData], days_to_keep: int = 30) -> bool:
        """
        Export pool data to 'Log' sheet for time-series tracking.

        Creates multiple rows per timestamp (one row per pool) with consistent columns.
        Automatically cleans up rows older than specified days.

        Args:
            pools: List of PoolData objects
            days_to_keep: Number of days of history to retain (default: 30)

        Returns:
            True if successful
        """
        if not pools:
            print("No pool data to log")
            return False

        client = self._get_client()
        if not client:
            return False

        try:
            spreadsheet = client.open_by_key(self.sheet_id)
        except Exception as e:
            print(f"Error accessing spreadsheet for log: {e}")
            return False

        sorted_pools = sorted(pools, key=lambda p: (p.chain, p.name))

        sheet_name = "Log"
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except:
            worksheet = spreadsheet.add_worksheet(
                title=sheet_name,
                rows=10000,
                cols=20
            )

            headers = [
                'Date', 'Time', 'Pool Name', 'Chain', 'Coins',
                'TVL (USD)', 'Base APY (%)', 'BAL Rewards Min (%)', 'BAL Rewards Max (%)',
                'Other Rewards (%)', 'Total APY (%)', 'Aura APY (%)', 'Aura TVL (USD)',
                'Aura Staking Contract', 'Address'
            ]

            worksheet.update(values=[headers], range_name='A1')
            print(f"Created Log sheet with headers")

        self._cleanup_old_log_data(worksheet, days_to_keep=days_to_keep)

        now = datetime.now()  # Local time for consistency with cron logs
        date_str = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M:%S')

        rows_to_append = []
        for pool in sorted_pools:
            other_rewards_val = sum(r['apy'] for r in pool.other_rewards) if pool.other_rewards else 0

            coins_str = "/".join(pool.coins[:4])
            if len(pool.coins) > 4:
                coins_str += "..."

            row = [
                date_str,
                time_str,
                pool.name,
                pool.chain.title(),
                coins_str,
                pool.tvl,
                pool.base_apy,
                pool.bal_rewards_apy[0] if pool.bal_rewards_apy else 0,
                pool.bal_rewards_apy[1] if len(pool.bal_rewards_apy) > 1 else 0,
                other_rewards_val,
                pool.total_apy,
                pool.aura_apy if pool.aura_apy is not None else "",
                pool.aura_tvl if pool.aura_tvl is not None else "",
                pool.aura_staking_contract if pool.aura_staking_contract else "",
                pool.address
            ]
            rows_to_append.append(row)

        try:
            if rows_to_append:
                worksheet.insert_rows(rows_to_append, row=2, value_input_option='USER_ENTERED')
                print(f"Logged {len(rows_to_append)} pool snapshots at {date_str} {time_str}")
            return True
        except Exception as e:
            print(f"Error inserting to Log sheet: {e}")
            return False


class BalancerTracker:
    """Main tracker class - fetches data and saves to data store"""

    def __init__(self, data_store: PoolDataStore = None, enable_aura: bool = False):
        self.api = BalancerAPI()
        self.data_store = data_store or PoolDataStore()
        self.enable_aura = enable_aura
        self.aura_api = AuraFinanceAPI() if enable_aura else None

    def _parse_pool(self, pool_data: Dict, chain: str, aura_enabled: bool = False) -> Optional[PoolData]:
        """Parse API response into PoolData object"""
        if not pool_data:
            return None

        dynamic = pool_data.get('dynamicData', {})

        # Parse TVL
        tvl = float(dynamic.get('totalLiquidity', 0) or 0)

        # Parse APR items
        apr_items = dynamic.get('aprItems', [])
        base_apy = 0.0
        bal_base = 0.0  # VEBAL_EMISSIONS - base BAL rewards
        bal_boost = 0.0  # STAKING_BOOST - additional boost with veBAL
        other_rewards = []

        for item in apr_items:
            apr_type = item.get('type', '')
            title = item.get('title', '')
            apr_value = float(item.get('apr', 0) or 0) * 100  # Convert to percentage
            token_symbol = item.get('rewardTokenSymbol', '')

            if apr_type == 'SWAP_FEE_24H':
                base_apy = apr_value
            elif apr_type == 'VEBAL_EMISSIONS':
                # Base BAL rewards (min without boost)
                bal_base = apr_value
            elif apr_type == 'STAKING_BOOST':
                # Additional BAL rewards with veBAL boost
                bal_boost = apr_value
            elif apr_value > 0:
                other_rewards.append({
                    'token': title,
                    'apy': apr_value
                })

        # BAL rewards: min = base, max = base + boost
        bal_rewards = [bal_base, bal_base + bal_boost]

        # Calculate total APY
        total_apy = base_apy + bal_rewards[0] + sum(r['apy'] for r in other_rewards)

        # Parse tokens
        coins = []
        coin_ratios = []
        coin_amounts = []
        coin_prices = []

        for token in pool_data.get('poolTokens', []):
            symbol = token.get('symbol', 'Unknown')
            balance = float(token.get('balance', 0) or 0)
            weight = token.get('weight')

            coins.append(symbol)
            coin_amounts.append(balance)

            # Calculate ratio
            if weight:
                ratio_pct = float(weight) * 100
            else:
                # For non-weighted pools, estimate equal distribution
                ratio_pct = 100 / len(pool_data.get('poolTokens', [1]))

            coin_ratios.append(f"{symbol}: {ratio_pct:.1f}%")

            # Price placeholder (would need token price API for accurate prices)
            coin_prices.append(0.0)

        # Aura data
        aura_apy = None
        aura_tvl = None
        aura_boost = None
        aura_staking_contract = None

        if self.aura_api and aura_enabled:
            pool_address = pool_data.get('address', '')
            aura_pool = self.aura_api.find_pool_by_balancer_address(pool_address, chain)

            if aura_pool:
                # Calculate Aura APR using max BAL boost
                bal_max_apr = bal_rewards[1]  # Max BAL APR (with full boost)
                aura_apr_data = self.aura_api.calculate_aura_apr(aura_pool, tvl, bal_max_apr)

                if aura_apr_data:
                    # Total Aura APY = base + max BAL + AURA rewards + other
                    aura_apy = base_apy + aura_apr_data.get('total_apr', 0) + sum(r['apy'] for r in other_rewards)

                # Calculate Aura TVL
                dynamic = pool_data.get('dynamicData', {})
                total_shares = float(dynamic.get('totalShares', 0) or 0)
                bpt_price = tvl / total_shares if total_shares > 0 else 1.0
                aura_tvl = self.aura_api.get_aura_tvl(aura_pool, bpt_price)

                # Boost is implicit - Aura gives max boost to all depositors
                aura_boost = 2.5  # Max veBAL boost is 2.5x

                # Get Aura staking contract (rewardPool)
                aura_staking_contract = aura_pool.get('rewardPool')

        return PoolData(
            name=pool_data.get('name', 'Unknown'),
            chain=chain,
            address=pool_data.get('address', ''),
            pool_id=pool_data.get('id', ''),
            tvl=tvl,
            base_apy=base_apy,
            bal_rewards_apy=bal_rewards,
            other_rewards=other_rewards,
            total_apy=total_apy,
            coins=coins,
            coin_ratios=coin_ratios,
            coin_amounts=coin_amounts,
            coin_prices=coin_prices,
            aura_apy=aura_apy,
            aura_tvl=aura_tvl,
            aura_boost=aura_boost,
            aura_staking_contract=aura_staking_contract
        )

    def get_pool(self, chain: str, identifier: str, aura_enabled: bool = False) -> Optional[PoolData]:
        """Get single pool data"""
        pool_data = self.api.find_pool(identifier, chain)
        return self._parse_pool(pool_data, chain, aura_enabled)

    def track_pools(self, pools_config: List[Dict]) -> List[PoolData]:
        """
        Track multiple pools from config.

        Args:
            pools_config: List of pool configs with 'chain', 'pool', optional 'aura_enabled'

        Returns:
            List of PoolData objects
        """
        results = []

        # Group by chain for efficient batching
        by_chain = {}
        for cfg in pools_config:
            chain = cfg.get('chain', 'ethereum')
            if chain not in by_chain:
                by_chain[chain] = []
            by_chain[chain].append(cfg)

        for chain, pool_configs in by_chain.items():
            print(f"Fetching {len(pool_configs)} pools from {chain}...")

            # Collect addresses for batch query
            addresses = [cfg['pool'] for cfg in pool_configs]

            # Check if any are full pool IDs vs addresses
            full_ids = [a for a in addresses if len(a.replace('0x', '')) > 42]
            short_addrs = [a for a in addresses if len(a.replace('0x', '')) <= 42]

            # Batch fetch by address
            if short_addrs:
                pools = self.api.get_pools_by_address(short_addrs, chain)
                for pool_data in pools:
                    # Find matching config
                    addr = pool_data.get('address', '').lower()
                    cfg = next((c for c in pool_configs if c['pool'].lower() == addr), {})
                    aura_enabled = cfg.get('aura_enabled', False)

                    parsed = self._parse_pool(pool_data, chain, aura_enabled)
                    if parsed:
                        results.append(parsed)

            # Fetch full IDs individually
            for pool_id in full_ids:
                cfg = next((c for c in pool_configs if c['pool'] == pool_id), {})
                aura_enabled = cfg.get('aura_enabled', False)

                pool_data = self.api.get_pool_by_id(pool_id, chain)
                parsed = self._parse_pool(pool_data, chain, aura_enabled)
                if parsed:
                    results.append(parsed)

        return results

    def fetch_and_save(self, pools_config: List[Dict]) -> List[PoolData]:
        """Fetch pools and save to data store"""
        results = self.track_pools(pools_config)

        if results:
            self.data_store.save(results)
            self.data_store.append_history(results)

        return results


def format_currency(amount: float) -> str:
    """Format currency with appropriate suffixes"""
    if amount >= 1_000_000_000:
        return f"${amount/1_000_000_000:.2f}B"
    elif amount >= 1_000_000:
        return f"${amount/1_000_000:.2f}M"
    elif amount >= 1_000:
        return f"${amount/1_000:.2f}K"
    else:
        return f"${amount:.2f}"


def print_results(pool_data_list: List[PoolData]):
    """Print results in tabular format"""
    if not pool_data_list:
        print("No pool data found.")
        return

    # Check if any pools have Aura data
    has_aura = any(p.aura_apy is not None for p in pool_data_list)

    headers = [
        "Pool Name",
        "Chain",
        "Coins",
        "TVL",
        "Base APY",
        "BAL Rewards",
        "Other Rewards",
        "Min APY"
    ]

    if has_aura:
        headers.extend(["Aura APY", "Aura TVL"])

    rows = []
    for pool in pool_data_list:
        # Format BAL rewards
        if pool.bal_rewards_apy and len(pool.bal_rewards_apy) >= 2:
            if pool.bal_rewards_apy[0] == pool.bal_rewards_apy[1]:
                bal_str = f"{pool.bal_rewards_apy[0]:.2f}%"
            else:
                bal_str = f"{pool.bal_rewards_apy[0]:.2f}-{pool.bal_rewards_apy[1]:.2f}%"
        else:
            bal_str = "0.00%"

        # Format other rewards
        if pool.other_rewards:
            rewards_list = [f"{r['token']}: {r['apy']:.2f}%" for r in pool.other_rewards[:2]]
            other_str = ", ".join(rewards_list)
            if len(pool.other_rewards) > 2:
                other_str += "..."
        else:
            other_str = "-"

        # Format coins
        coins_str = "/".join(pool.coins[:3])
        if len(pool.coins) > 3:
            coins_str += "..."

        row = [
            pool.name[:35] + "..." if len(pool.name) > 35 else pool.name,
            pool.chain.title(),
            coins_str,
            format_currency(pool.tvl),
            f"{pool.base_apy:.2f}%",
            bal_str,
            other_str,
            f"{pool.total_apy:.2f}%"
        ]

        if has_aura:
            aura_apy_str = f"{pool.aura_apy:.2f}%" if pool.aura_apy is not None else "-"
            aura_tvl_str = format_currency(pool.aura_tvl) if pool.aura_tvl else "-"
            row.extend([aura_apy_str, aura_tvl_str])

        rows.append(row)

    print("\n" + tabulate(rows, headers=headers, tablefmt="grid"))
    print(f"\nTotal pools: {len(pool_data_list)}")


def load_pools_config(filepath: str = None) -> tuple[List[Dict], bool]:
    """
    Load pools config from JSON file.

    Returns:
        Tuple of (pools_list, aura_enabled_global)
    """
    filepath = filepath or 'pools.json'

    if not os.path.exists(filepath):
        return [], False

    try:
        with open(filepath, 'r') as f:
            config = json.load(f)

        if isinstance(config, dict):
            aura_enabled = config.get('settings', {}).get('aura_enabled', False)
            pools = config.get('pools', [])
            return pools, aura_enabled
        elif isinstance(config, list):
            return config, False
        else:
            return [], False

    except json.JSONDecodeError as e:
        print(f"Error parsing {filepath}: {e}")
        return [], False


def main():
    parser = argparse.ArgumentParser(description="Track Balancer pool metrics")

    # Pool selection
    parser.add_argument('--chain', '-c', default='ethereum',
                       help='Blockchain (default: ethereum)')
    parser.add_argument('--pool', '-p',
                       help='Single pool address or ID')
    parser.add_argument('--pools', '-P',
                       help='JSON file with pool list (default: pools.json)')
    parser.add_argument('--top', type=int,
                       help='Show top N pools by TVL')

    # Aura integration
    parser.add_argument('--aura', action='store_true',
                       help='Enable Aura Finance data fetching')

    # Output control
    parser.add_argument('--no-json', action='store_true',
                       help='Disable saving to JSON (print only)')
    parser.add_argument('--quiet', '-q', action='store_true',
                       help='Minimal output')

    # Google Sheets export
    parser.add_argument('--export-sheets', action='store_true',
                       help='Export to Google Sheets')
    parser.add_argument('--credentials',
                       help='Path to Google credentials JSON (default: Google Credentials.json)')
    parser.add_argument('--sheet-id',
                       help='Google Sheet ID to export to')

    args = parser.parse_args()

    # Initialize
    data_store = PoolDataStore()

    # Load config
    pools_config, config_aura_enabled = load_pools_config(args.pools)
    enable_aura = args.aura or config_aura_enabled

    tracker = BalancerTracker(data_store=data_store, enable_aura=enable_aura)

    if enable_aura:
        print("Aura Finance integration enabled")

    # Determine what to fetch
    results = []

    if args.pool:
        # Single pool
        pool_data = tracker.get_pool(args.chain, args.pool, aura_enabled=enable_aura)
        if pool_data:
            results = [pool_data]
    elif args.top:
        # Top pools by TVL
        print(f"Fetching top {args.top} pools on {args.chain}...")
        top_pools = tracker.api.get_top_pools(args.chain, limit=args.top)
        for pool_data in top_pools:
            parsed = tracker._parse_pool(pool_data, args.chain)
            if parsed:
                results.append(parsed)
    elif pools_config:
        # From config file
        results = tracker.track_pools(pools_config)
    else:
        print("No pools configured.")
        print("Use --pool ADDRESS, --top N, or configure pools.json")
        sys.exit(0)

    # Save to JSON unless disabled
    if not args.no_json and results:
        data_store.save(results)
        data_store.append_history(results)

    # Print results
    if not args.quiet:
        print_results(results)

    # Export to Google Sheets if requested
    if args.export_sheets and results:
        exporter = GoogleSheetsExporter(
            credentials_path=args.credentials,
            sheet_id=args.sheet_id
        )
        exporter.export(results, pools_config)
        exporter.export_to_log_sheet(results)


if __name__ == "__main__":
    main()
