# Video splitting performance — 2026-11-23

Base: `c81b85c05cc6422cb1d728baa446e932a08a9eee` (master when this task began).
Implementation: `96ec526` (`perf/offline-profile-2026-11-23`).

## Change

A source file's bitrate can be much lower than the bitrate produced by the
existing H.264 CRF 18 encoder. Previously, each part started with the duration
estimated from the source file. If that encoded part exceeded 50 MiB, the bot
threw it away and encoded a shorter interval. The next part repeated the same
optimistic estimate and often wasted another complete encode.

After a size retry, the splitter now uses the accepted output's bytes per second
to estimate later intervals, retaining the existing 45 MiB target and the
original duration as a ceiling. Intervals can grow again when scene complexity
falls. Encoding quality, codecs, exact seeking, timestamp precision, audio and
the per-file size validation remain the same.

Two safeguards handle the new boundaries:

- Balance the final two adaptive intervals so an estimated boundary does not
  leave a sub-frame tail without video.
- Allow one extra size correction on an adaptive interval. If these corrections
  still fail, clean the entire unsuccessful pass and retry the original strategy
  once. Other failures do not restart the job. This fallback can be slower on
  unusually bursty video, but retains the original strategy for inputs it handled.

The initial two-attempt behavior and intervals stay unchanged for videos that
never need adaptive splitting. Short videos that do not need splitting are
unaffected. No downloader, Telegram handler, dependency or README changes are
included.

## Reproduce

From this branch with ffmpeg/ffprobe installed:

```sh
uv sync --frozen --extra dev
uv run --frozen python benchmarks/benchmark_split.py \
  --base-ref c81b85c05cc6422cb1d728baa446e932a08a9eee \
  --rounds 3 --case full_limit --case landscape --case portrait \
  --case no_retry --case concurrent --output /tmp/tgdlbot-split-results.json
```

The harness reads the old `media.py` from Git without switching the checkout.
It generates local media, alternates before/after order, times splitting, and
then checks outputs outside the measured interval. Raw JSON includes each encode's
start, duration, output size and elapsed time. Temporary media is removed on exit.
There are no external downloads or Telegram calls; a dummy token replaces the
inherited token before configuration loads, and dotenv loading is disabled.

## Measurements

Environment: Python 3.14.10, ffmpeg version 7.1.5-0+deb13u1 Copyright (c) 2000-2026 the FFmpeg developers; x86_64,
5 visible vCPUs, CPU quota of 4 cores (400000/100000). No other test suite
ran on the machine during the final benchmark. Three repetitions per case;
order before/after, after/before, before/after. Times are wall-clock seconds,
including splitter instrumentation and thread-pool overhead.

| Scenario | Before, median (range), s | After, median (range), s | Reduction | Encodes before → after |
| --- | ---: | ---: | ---: | ---: |
| 1080p, 144 s, actual 50 MiB limit | 266.34 (265.19–271.06) | 156.06 (154.80–166.20) | 41.4% | 7 → 5 |
| 720p landscape, 12 s, scaled limit | 10.82 (10.71–10.86) | 6.07 (5.86–6.09) | 43.9% | 9 → 6 |
| 720×1280 portrait, 12 s, scaled limit | 10.38 (10.26–11.19) | 6.58 (6.48–6.67) | 36.6% | 9 → 7 |
| 720p, 12 s, no size retries | 5.24 (3.67–7.62) | 6.46 (3.62–7.50) | — | 2 → 2 |
| Three concurrent 720p splits, 12 s each | 35.28 (29.96–40.94) | 15.73 (15.69–16.20) | 55.4% | 27 → 18 |

All samples, in round order:

| Scenario | Before, s | After, s | Source / limit, MiB | Parts per job, before → after |
| --- | --- | --- | --- | --- |
| 1080p, 144 s, actual 50 MiB limit | 271.06, 265.19, 266.34 | 156.06, 154.80, 166.20 | 50.918 / 50.000 | 4 → 4 |
| 720p landscape, 12 s, scaled limit | 10.82, 10.86, 10.71 | 6.07, 6.09, 5.86 | 1.134 / 0.756 | 5 → 5 |
| 720×1280 portrait, 12 s, scaled limit | 11.19, 10.38, 10.26 | 6.58, 6.67, 6.48 | 1.213 / 0.809 | 5 → 5 |
| 720p, 12 s, no size retries | 5.24, 7.62, 3.67 | 6.46, 7.50, 3.62 | 14.389 / 9.592 | 2 → 2 |
| Three concurrent 720p splits, 12 s each | 40.94, 29.96, 35.28 | 15.73, 16.20, 15.69 | 1.134 / 0.756 | 5 → 5 |

No speedup is claimed for the no-retry control: it executes the same encoding
intervals, and three samples do not establish a timing change. Concurrent timings
are the makespan for all three jobs. Encode counts there are summed across jobs.

The actual-limit fixture contains 4,320 frames; each variant preserves all of
them. Avoiding discarded encodes is the measured improvement, not a change to
the quality preset or skipping media validation.

Candidate `media.py` SHA-256: `9887b8ef1f1404024d96983f53afb2fd9148b121ce968a7a1bc70b4337a4d613`.

## Validation

`TELEGRAM_BOT_TOKEN=000000:offline-test PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest tests/ -q`

Local result: **245 passed, 17 subtests passed**, in 31.28 seconds. The existing
pytest-asyncio fixture-scope warning and three python-telegram-bot deprecation
warnings remain. `git diff --check` passed.

Tests cover stable/falling/rising encoded bitrate, a short bitrate burst,
exhausted adaptive attempts falling back to the original strategy, cleanup,
source preservation, and a real encoded 0.01-second-tail regression. Existing
real-FFmpeg tests verify numbered frames exactly once and in order across
boundaries, fractional/VFR timestamps, long GOPs, B-frames and audio alignment.
New failure cases were observed failing before their fixes.

Every benchmark output is checked for a positive size within its configured
limit, decodable video, expected resolution, H.264/AAC codecs, audio/video duration
agreement within 150 ms and total decoded frame count equal to its source.
The source's SHA-256 is unchanged. These checks are outside the measured interval.

## Limits of these results

- This measures local splitting, not end-to-end download or Telegram upload.
  Network latency and platform behavior were not measured.
- Inputs are deterministic generated patterns, not a representative sample of
  real user downloads. The full-limit source repeats a six-second noisy seed.
- The landscape, portrait, no-retry and concurrent cases use a smaller limit to
  exercise the same splitting path with short fixtures. Such small videos would
  normally upload without splitting at the real 50 MiB limit.
- The full-limit case uses the actual 50 MiB limit and a source larger than it.
- The cloud machine is x86_64; production Raspberry Pi/ARM64 timing is not claimed.
  Wall-clock measurements can vary with shared-host scheduling. Each comparison
  uses the same encoder settings and source, and run order alternates.
- Very irregular bitrate can require the original-strategy fallback, repeating
  work and making that job slower. Retries remain bounded; this change does not
  promise successful processing of every source the original bot also rejected.
- No live bot was started, no production configuration was changed, and no merge
  or deployment was performed.
