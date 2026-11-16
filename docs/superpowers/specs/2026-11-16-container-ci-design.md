# Automatic container builds on master

Build both existing Docker targets on every push to `master` and publish them
to GitHub Container Registry, as requested. Pull requests targeting `master`
also build and test, without publishing. Allow manual runs; only `master` may
publish. Use `linux/amd64`, matching the current Docker environment.

## Approach

GitHub Actions and GHCR reuse the repository's existing GitHub hosting and
`GITHUB_TOKEN`; the user selected GHCR. Docker Hub would need another account
and credentials. Build-only CI would not provide downloadable images.

Use separate `build`, `test`, and `publish` jobs. Build the `test` and `production`
targets in a matrix with Buildx and separate GitHub Actions cache scopes. Export
Docker archives as artifacts retained for three days. The test matrix loads
those archives, runs the test image offline, and runs the existing
FFmpeg unittest suites (splitting, previews, and dimensions) in the production
image. Push those exact tested local
images only after both checks pass. The publish job downloads the original
archives and is the only job with `packages: write`. Keep credentials out of
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
