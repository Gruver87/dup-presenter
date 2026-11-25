---
slug: md-talk-demo
lang: en
theme: cosmic_radar
caption_style: karaoke
---
## [hero_3d] Radar for crypto markets
tag: OVERVIEW
subtitle: A hybrid Python and Rust watchlist
voice: DUP Market Radar is a hybrid Python and Rust watchlist for the crypto market.
It tracks spot pairs, watch-only futures, memes, stablecoins and new listings.

## [kpi] Numbers
tag: METRICS
voice: The numbers below come from the project's own test and config files.
- 4488 :: instruments in the catalogue
- 0 :: floats in money paths
- 2 :: venues for manual orders

## [timeline] How a scan works
tag: PIPELINE
voice: Each scan runs the same four steps, in the same order.
- Fetch :: pull market data from the venue
- Score :: rank instruments with the heuristic
- Filter :: drop anything below the threshold
- Show :: publish the watchlist to the dashboard

## [outro_3d] Thank you
tag: SUMMARY
url: github.com/Gruver87/dup-market-radar
tagline: Heuristic rankings do not guarantee profit
voice: The project is open source. Heuristic scores never guarantee profit, so decide for yourself.
