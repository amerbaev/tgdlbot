# Container CI Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan.

**Goal:** Build, test, and publish both Docker targets when master changes.

**Architecture:** Separate build and test matrix jobs pass Docker archives as
artifacts. A publish job pushes the tested images only on master. PRs run the
same build and tests without registry authentication or publication. Compose
uses GHCR by default and an explicit overlay keeps local development available.

**Tech Stack:** GitHub Actions, Docker Buildx, GHCR, actionlint.

**Spec:** `docs/superpowers/specs/2026-11-16-container-ci-design.md`

## Global Constraints

- Publish only on `master`, using `GITHUB_TOKEN` and `packages: write`.
- Build both `production` and `test` for `linux/amd64` and `linux/arm64`.
- Tests run offline without bot credentials; production runs as its existing user.
- Publish tested images without rebuilding them; use full commit SHA tags.
- Do not change the application, dependencies, or deployment configuration.

## Review Focus

- Pull requests and manual runs on other branches must not publish.
- A test failure must prevent every registry push.
- FFmpeg tests skipped in the test image must run in production.
- Concurrent master runs must not publish mutable tags out of order.
- GHCR visibility and credentials must be accurately documented.

## Task 1: Workflow and usage documentation

**Files:** Create `.github/workflows/images.yml`; update `README.md`.

**Interfaces:** Existing Docker targets and offline test commands in README;
produce the GHCR tags described in the spec.

- [x] Add push, pull_request, and workflow_dispatch triggers, concurrency,
  least required permissions, cached builds, tests, and guarded publication.
- [x] Document triggers, tags, architecture, pull/run commands, and GHCR setup.
- [x] Run actionlint on the workflow; expect exit 0.
- [x] Build both Docker targets, run the test image and production FFmpeg suite;
  expect exit 0 (FFmpeg skips in test are covered in production).
- [x] Review event guards, failure behavior, tags, and `git diff --check`.

Delivery: commit and open a pull request; verify the GitHub Actions run.

## Validation record

Actionlint 1.7.7 and `git diff --check` pass. Both Docker targets build using
the managed environment's temporary CA secret mounts. The offline test image
passes 228 tests (11 FFmpeg tests skipped, three existing dependency warnings).
Production unittest discovery passes all 11 FFmpeg tests, including the preview
and dimension suites added to CI after review.

## Follow-up: Separate CI jobs and use GHCR in Compose

Requested after the initial PR was merged. Preserve the existing tags and
master/PR/manual event rules, using `packages: write` only in `publish`.

- [x] Split build/test/publish; transfer the original Docker archives using
  uniquely named artifacts retained for three days, without rebuilding.
- [x] Switch both Compose services to GHCR with configurable tags and always-pull;
  add an explicit local-build overlay and update Makefile, README, and AGENTS.md.
- [x] Check actionlint, default/pinned/local Compose configurations and Makefile
  commands. Run the published test image through Compose: 228 passed,
  11 FFmpeg skips, three existing dependency warnings.

Delivery verification: run the workflow in a pull request to verify archive
export/load and transfer, both matrices, and skipped publication for pull requests.

## Fix: Raspberry Pi 5 support (2026-11-17)

The registry manifest identified the published image as amd64. The user runs
Raspberry Pi 5 (ARM); the Python executable fails before the application starts.
The Python and uv base images and locked native dependencies support ARM64.

- [x] Configure both targets on native amd64 and ARM64 runners with isolated caches,
  artifact paths, and Docker tags; test each image on its own architecture.
- [x] Add a runtime architecture/Python startup check, then run the existing
  offline and FFmpeg suites for each architecture.
- [x] Assemble multi-platform indexes from the tested archives in publish;
  verify both platforms before updating latest/master/test aliases.
- [x] Update README with automatic platform selection, 64-bit Raspberry Pi OS,
  and recovery commands for the previous amd64-only image.

Verification: actionlint, native amd64 startup check locally, and the full
GitHub Actions matrix including native ARM64 builds and tests. The multi-platform
registry aliases become available after the fix is merged and published.

Local checks: actionlint and diff check pass. The current image passes amd64
startup validation and fails the ARM64 predicate as expected. Buildx dry-run
assembly of two existing platform manifests passes the publication guard;
the same guard rejects an amd64-only index. Independent review found no issues.
