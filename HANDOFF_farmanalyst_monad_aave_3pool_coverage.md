# HANDOFF → BalancerTracker — add Monad "Aave 3-pool"; you're tracking the lookalike instead

**From:** farmAnalyst · **Date:** 2026-08-19 · **Coverage gap. One pool to add, one naming trap to encode.**

## Ask

Add **`0xDAaE80492fdA633B5D0375b22EEDC5c7B422fb4C`** — Balancer V3, Monad, symbol **"Aave 3-pool"**,
legs `waMonUSDT0 / waMonAUSD / waMonUSDC`. Personal USD is migrating ~$34k into it this week.

## Why it matters more than a normal add

`data/balancer_pools_latest.json` currently tracks `monad_wnausd_wnusdc_wnusdt0`
(`0x2DAA146dfB7EAef0038F9F15B2EC1e4DE003f72b`). **That is a different protocol's pool.**

| | tracked | should also track |
|---|---|---|
| Address | `0x2DAA146d…f72b` | `0xDAaE8049…fb4C` |
| Legs | `wnUSDT0 / wnAUSD / wnUSDC` | `waMonUSDT0 / waMonAUSD / waMonUSDC` |
| Wrapper | **Neverland** (`wn`) | **Aave** static aTokens (`waMon`) |
| TVL | $3,392,489 | $971,586 |
| Merkl APR | 4.92% | 8.05–10.59% |
| Total APR | ~6.9% | **10.58–13.12%** |

Same three underlying assets, near-identical ticker sets, addresses that both start `0x?DAA…`/`0xDAaE…`.
The only distinguishing signal is the **`wn` vs `waMon` prefix**. This is the same class of trap as the
`reUSD` / `msUSD` / `USD3` ticker collisions farmAnalyst hit in July — a symbol-level match would pick the
wrong pool and attach a yield that's off by 2×.

**Suggestion:** encode the wrapper family explicitly in the pool record (e.g. `wrapper: "aave" | "neverland"`)
rather than relying on the display name, and keep the full address in the id. A consumer joining on
"monad tristable USDT0/AUSD/USDC" will otherwise pick whichever it saw first.

## Pool data (verified 2026-08-19 via `api-v3.balancer.fi`)

```
poolGetPool(id:"0xdaae80492fda633b5d0375b22eedc5c7b422fb4c", chain:MONAD)
  name "Aave 3-pool"   type STABLE   swapFee 0.000005
  totalLiquidity  $971,586      volume24h $56,075
  waMonUSDT0  596,219.49  $597,707   (61.5%)
  waMonAUSD   190,957.88  $191,613   (19.7%)
  waMonUSDC   181,491.70  $182,266   (18.8%)
  aprItems:
    Merkl Rewards   MERKL      10.590%
    waMonUSDT0 APR  IB_YIELD    1.544%
    waMonUSDC APR   IB_YIELD    0.558%
    waMonAUSD APR   IB_YIELD    0.432%
```

⚠️ **Merkl's own API reports this campaign at 8.046%, Balancer computes 10.590%.** Worth deciding which you
publish, and labelling it — a 2.5pp gap on the dominant APR component is not a rounding difference. If you
publish Balancer's, consider carrying Merkl's alongside as a cross-check field; farmAnalyst would rather see
both than pick blind.

## Two other Monad pools you may want while you're in here

Both are live, both larger than pools you already track, neither is in `balancer_pools_latest.json`:

| pool | address | TVL | APR |
|---|---|---:|---:|
| Avant `avUSD-AUSD` | `0x234B49e87A7Fff921A060c21D2C013291BBD7fF1` | $3,370,900 | 8.22% |
| `Aave USDe-USDT0` | `0xf40A707Ab16c9BA7a72FAA3F282EcEbf7fEA1559` | $70,606 | 16.20% |

Balancer's Monad deployment has **36 pools**; you carry 3. Not arguing for all 36 — but the selection
currently misses the two largest stable pools on the chain.

## Verified

`api-v3.balancer.fi/graphql` `poolGetPool` / `poolGetPools(chainIn:[MONAD])` and
`api.merkl.xyz/v4/opportunities?chainId=143`, both read 2026-08-19.
