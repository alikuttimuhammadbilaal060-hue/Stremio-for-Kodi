# Raspberry Pi 3 performance pass

This is the repeatable low-power test pass for GitHub issue #47. The issue stays open until a real Raspberry Pi 3 result is reviewed.

## Before testing

1. Update Stremio for Kodi to the release that includes **Support → Run low-power benchmark**.
2. Open Home once and let the background refresh finish.
3. Do not play video while taking the benchmark sample.

## Run the local benchmark

Open **Settings → Support → Run low-power benchmark**. The benchmark performs no network requests and measures five samples of each local path, reporting the median:

- **Cached Home** target: ≤ 350 ms
- **Snapshot read** target: ≤ 150 ms
- **Continue Watching SQLite** target: ≤ 120 ms
- **Account state read** target: ≤ 80 ms
- **Stream cache SQLite** target: ≤ 120 ms

These are provisional engineering budgets, not a substitute for a real Pi 3 test.

Then choose **Settings → Support → Send performance report**. Review the privacy-safe payload before sending. It contains timing/count data, broad software/platform versions and a broad hardware class only; it does not read kodi.log, titles, URLs, tokens, API keys, account data or device IDs.

## Couch test

Using only the TV remote, verify:

1. Home cached content appears promptly after launch.
2. Vertical and horizontal row navigation remains responsive for at least 60 seconds.
3. Infinite Home pagination loads the next page near the end of a row without freezing navigation.
4. Details → Streams opens once from uncached state and again from SQLite cache; the second open should not feel slower than the first.
5. Start and stop one episode; returning to Home and the episode list should refresh Continue Watching/watched state without a long pause.
6. Leave the addon using Back/Exit and confirm there is no focus trap.

## Low-power rules that must remain true

- Home snapshots are display-only and each initial row is capped at 16 cards.
- Catalog refresh uses at most two workers.
- Account/library/Continue Watching maintenance stays off the critical Home navigation path.
- Changed Home rows are patched instead of rebuilding the entire window where possible.
- Stream prefetch is bounded and does not run during playback.
- AI/network-heavy work must not block ordinary Home/Details navigation.

Record the benchmark report and any visible navigation regression on issue #47. Close #47 only after a real Pi 3 pass has evidence for these checks.
