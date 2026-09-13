# Dinner Table News — fetcher

Hourly GitHub Action that pulls the allowlisted feeds in `feeds.yaml` and writes
`data/headlines.json` (last 48 hours, deduped). Downstream, the scheduled Claude task
reads that file to pick the day's three stories and build the carousel.

Add or remove a source by editing `feeds.yaml`. Nothing outside that file is ever fetched.
