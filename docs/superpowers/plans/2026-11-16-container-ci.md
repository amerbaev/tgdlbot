# Container CI Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan.

**Goal:** Build, test, and publish both Docker targets when master changes.

**Architecture:** One GitHub Actions job builds and tests the existing images,
then authenticates and pushes the tested images only on master. PRs run the
same build and tests without registry authentication or publication.

**Tech Stack:** GitHub Actions, Docker Buildx, GHCR, actionlint.

**Spec:** `docs/superpowers/specs/2026-11-16-container-ci-design.md`

## Global Constraints

- Publish only on `master`, using `GITHUB_TOKEN` and `packages: write`.
- Build both `production` and `test` for `linux/amd64`.
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
