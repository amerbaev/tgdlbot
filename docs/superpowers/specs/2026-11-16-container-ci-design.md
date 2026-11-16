# Automatic container builds on master

Build both existing Docker targets on every push to `master` and publish them
to GitHub Container Registry, as requested. Pull requests targeting `master`
also build and test, without publishing. Allow manual runs; only `master` may
publish. Support `linux/amd64` and `linux/arm64`, including Raspberry Pi 5 on
a 64-bit OS. The original amd64-only image failed on the user's Raspberry Pi
with `exec /app/.venv/bin/python: exec format error`.

## Approach

GitHub Actions and GHCR reuse the repository's existing GitHub hosting and
`GITHUB_TOKEN`; the user selected GHCR. Docker Hub would need another account
and credentials. Build-only CI would not provide downloadable images.

Use separate `build`, `test`, and `publish` jobs. Build the `test` and `production`
targets on native amd64 and ARM64 runners, with Buildx and separate cache scopes
and artifact names per target/architecture. Export
Docker archives as artifacts retained for three days. The test matrix loads
those archives, runs the test image offline, and runs the existing
FFmpeg unittest suites (splitting, previews, and dimensions) in the production
image. Push those exact tested local
images only after both checks pass. The publish job downloads the original
archives, pushes architecture-specific commit tags, and combines them into
multi-platform indexes without rebuilding. Verify both platforms are present
before updating mutable tags. This is the only job with `packages: write`.
Check image metadata and Python startup on each native runner before the suite.
Keep credentials out of
containers and disable checkout credential persistence.

Publish `ghcr.io/amerbaev/tgdlbot` with production tags `latest`, `master`, and
`sha-<full commit SHA>`, and test tags `test` and `test-sha-<full commit SHA>`.
Serialize master runs so simultaneous builds cannot publish out of order.
Document image use, permissions, and the initial private visibility of GHCR
packages. Compose uses GHCR images by default with an always-pull policy and
configurable production/test tags. An explicit `docker-compose.build.yml`
overlay preserves local builds through Makefile development commands.
Application behavior, dependencies, and changes to a running server are outside
this change. Validate the workflow with actionlint, render both Compose modes,
and execute its Docker checks.
