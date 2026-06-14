# BalancerTracker → DexTracker Hand-off

> **From:** DexTracker LP risk engine (`/home/danger/DexTracker/lp_risk_engine.py`)
> **Date:** 2026-06-15
> **Ask:** Emit complete, value-correct Balancer pool data in `data/balancer_pools_latest.json` so DexTracker can **consume** it (like it does Mento) instead of re-fetching the Balancer API + on-chain router itself.

## Why this exists

DexTracker's LP risk digest reads Balancer pool state. Today it depends on BalancerTracker only for *pool discovery* (token-set match), then **re-fetches everything live itself** (reserves, prices, TVL, swap quotes) via the Balancer v3 API and on-chain router RPC inside `BalancerQuoteAdapter`. That's the wrong boundary: every other DEX here (Mento, SparkDex, Velodrome, LFJ) follows "tracker produces `*_latest.json` → engine consumes." Balancer is the only one where the consumer re-does the producer's job.

The trigger: **the `ratios` field is wrong.** It reports nominal pool weights, not real composition.

| Pool | BalancerTracker `ratios` (today) | Actual value-weighted (amount × price) |
|---|---|---|
| msUSD/USDC | `50.0 / 50.0` | **66.1 / 33.9** |
| syzUSD/wnAUSD | `50.0 / 50.0` | **59.0 / 41.0** |

A digest meant to catch pool imbalance/drain risk was showing a constant `50/50` that can never move — a blind spot for exactly the risk it exists to surface. DexTracker has applied an **interim** value-weighting fix inside its own engine (`BalancerQuoteAdapter._value_ratios`) so today's digest is correct, but that's a stopgap to be removed once this lands.

## Root cause (this repo)

`balancer_tracker.py` lines 851–875:

```python
# Calculate ratio
if weight:
    ratio_pct = float(weight) * 100      # ← nominal pool WEIGHT, not live composition
else:
    ratio_pct = 100 / len(...poolTokens) # ← equal-split estimate, also wrong
coin_ratios.append(f"{symbol}: {ratio_pct:.1f}%")
...
coin_prices.append(0.0)                  # ← prices never populated ("placeholder")
```

You already pull `balance`, `weight`, **and `priceRate`** per token in the GraphQL query (lines ~105, 156). The data to value-weight is in hand; the code just isn't using it.

## What to fix

### 1. Populate real per-token USD prices (required)
Replace the `coin_prices.append(0.0)` placeholder with actual USD prices. Options, in order of preference:
- The Balancer v3 API exposes token USD prices (per-token `token { ... }` USD price, or pool `dynamicData`/`tokenGetCurrentPrices`). Prefer this — same source, one call.
- You already have a CoinGecko price client in the Aura section (`fetch_all_prices`, `_price_cache`, `COINGECKO_IDS`). Reuse it as a fallback.
- For pure-stable pools, `priceRate` (already fetched) × the USD anchor is a serviceable last resort, but real prices are better.

### 2. Compute `ratios` as value-weighted (required)
```python
value_i  = balance_i * price_i
ratio_i  = value_i / sum(value)         # → "msUSD: 66.1%", ...
```
Replace the weight-based block at lines 865–872. This makes `ratios` reflect actual reserve composition for both weighted *and* stable/composable pools.

### 3. (Optional, phase 2) Emit an executable slippage ladder
This is what lets DexTracker drop its on-chain router path entirely. Emit a Mento-style fixed-tier `liquidity` block (see schema below). Two ways to source it without adding web3/RPC to this repo:
- **Balancer SOR via GraphQL** — `sorGetSwapPaths` on api-v3.balancer.fi returns expected output for a given input amount; probe at tiers `[1k, 10k, 50k, 100k]` selling each non-anchor leg into the USD anchor.
- If you'd rather not, skip it — DexTracker can keep computing the position-size-specific exit ladder itself (that part is legitimately holdings-relative and may stay engine-side).

## Target output schema (the consumer contract)

Per pool in `balancer_pools_latest.json`, DexTracker needs the `tokens` block fixed and (optionally) a `liquidity` block mirroring Mento's shape so the engine's existing `_flat_quote_slippage` reader works unchanged:

```jsonc
"tokens": {
  "coins":   ["msUSD", "USDC"],
  "ratios":  ["msUSD: 66.1%", "USDC: 33.9%"],   // value-weighted, NOT nominal weight
  "amounts": [976407.33, 499505.82],            // already correct
  "prices":  [0.9997, 1.0]                       // FIX: real USD prices, not 0.0
},
// optional phase-2 — lets DexTracker stop calling the v3 router itself:
"liquidity": {
  "source": "balancer_sor", "chain": "ethereum", "timestamp": "...",
  "tokenIn": "msUSD", "tokenOut": "USDC",
  "quotes": { "1000": {"slippage_bps": -3.1, "output_usd": 999.69}, "10000": {...}, "50000": {...}, "100000": {...} },
  "capacity_usd": 1475000, "status": "ok"
}
```

## Once shipped — DexTracker side (we handle this)

When `tokens.ratios` is value-weighted and `tokens.prices` is real:
1. Remove the interim `BalancerQuoteAdapter._value_ratios` workaround from the engine.
2. Resolve Balancer like Mento — read `ratios`/`amounts`/`prices`/`tvl` straight from the index; no Balancer API or router RPC in the risk engine.
3. If the optional `liquidity` ladder lands, the engine consumes it via `_flat_quote_slippage` (already implemented for Mento) and the whole `BalancerQuoteAdapter` API/RPC path can be deleted.

## Notes
- BalancerTracker runs daily at 7:30 AM (cron); DexTracker's digest at 9:35 AM — so a same-day fix here flows into that morning's digest.
- Other BalancerTracker consumers (Google Sheets export) also benefit from real prices/ratios, so this isn't DexTracker-only.
