# Local Build Setup for Zero-Cost CI

This guide explains how to set up local building and pushing of Marty artifacts to eliminate GitHub Actions costs.

## Overview

Instead of relying on expensive GitHub Actions runners for:
- Multi-platform Docker builds (10 services × 2 architectures)
- Cross-platform Python wheel compilation (macOS runners cost ~10x more)
- Extensive E2E test matrices

We build everything locally and push to free GitHub Container Registry (GHCR) and GitHub Releases.

## Prerequisites

### Required Tools

1. **Docker Desktop** with Buildx
   ```bash
   # Verify installation
   docker --version
   docker buildx version
   ```

2. **Rust toolchain**
   ```bash
   # Install via rustup
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   
   # Add linux target (for cross-compilation from macOS)
   rustup target add x86_64-unknown-linux-gnu
   ```

3. **Python 3.11+** with build tools
   ```bash
   # Verify installation
   python3 --version
   
   # Install maturin (for Rust-Python wheels)
   pip install maturin
   
   # Install build tools
   pip install build twine
   ```

4. **GitHub CLI**
   ```bash
   # Install on macOS
   brew install gh
   
   # Authenticate
   gh auth login
   ```

### GitHub Personal Access Token (PAT)

You need a PAT with the following scopes to push to GHCR:
- `write:packages` - Push Docker images and packages
- `read:packages` - Pull images and packages

**Creating a PAT:**

1. Go to https://github.com/settings/tokens
2. Click **"Generate new token"** → **"Generate new token (classic)"**
3. Give it a descriptive name: `GHCR Local Build Access`
4. Select scopes:
   - ☑️ `write:packages`
   - ☑️ `read:packages`
5. Click **"Generate token"**
6. **Copy the token immediately** - you won't see it again!

## Initial Setup

### 1. Authenticate to GHCR

Run the setup script to authenticate Docker to GitHub Container Registry:

```bash
make setup
```

Or manually:

```bash
./scripts/ghcr-setup.sh
```

This will:
- Prompt for your GitHub username
- Prompt for your PAT (input hidden)
- Authenticate Docker to `ghcr.io`
- Validate credentials
- Store credentials in Docker's credential helper (persists across sessions)

### 2. Verify Authentication

```bash
docker info | grep ghcr.io
```

You should see GHCR in the registry list.

## Building and Pushing

### Incremental Build (Recommended)

Builds only changed services based on git diff:

```bash
make build-push
```

Or:

```bash
./scripts/build-all-local.sh
```

This will:
1. Check for changes since last build (`.last-build-sha`)
2. Build only changed Python wheels (marty-credentials, marty-core, marty-msf)
3. Create GitHub release with wheels (tag: `dev-YYYYMMDD-SHA`)
4. Build only changed Docker services
5. Tag images as `latest` and `dev-YYYYMMDD-SHA`
6. Push all artifacts to GHCR

**Build time:** ~10-30 minutes (depends on what changed)

### Force Full Rebuild

Rebuilds everything regardless of changes:

```bash
make build-all
```

Or:

```bash
./scripts/build-all-local.sh --force
```

**Build time:** ~30-60 minutes (full rebuild)

### Build Without Pushing

Useful for testing locally before pushing:

```bash
./scripts/build-all-local.sh --skip-push
```

### Push Only (Skip Building)

If you already have images built:

```bash
make push-only
```

## Updating Dependencies

### Pull Latest Images

To update your local environment with latest pushed images:

```bash
make pull-all
```

### Update Python Package URLs

After building wheels, update marty-ui requirements.txt to use latest GitHub release:

```bash
make update-requirements
```

Or manually:

```bash
./scripts/update-requirements.sh
```

This updates `marty-ui/src/requirements.txt` with direct URLs to wheels from the latest GitHub release.

## Creating Releases

### Semantic Version Release

For production releases (v1.2.3):

```bash
make release
```

Or:

```bash
./scripts/release-helper.sh [VERSION]
```

This will:
1. Prompt for version number (X.Y.Z format)
2. Update version in all `pyproject.toml` and `Cargo.toml` files
3. Create git tag `vX.Y.Z`
4. Force rebuild all services
5. Push images with both `:latest` and `:vX.Y.Z` tags
6. Push git tag to origin

## Build Artifacts

### Docker Images

All images are tagged with:
- `ghcr.io/OWNER/REPO/SERVICE:latest` - Rolling latest
- `ghcr.io/OWNER/REPO/SERVICE:dev-YYYYMMDD-SHA` - Development build

Services:
- `csca-service`
- `document-signer`
- `dtc-engine`
- `inspection-system`
- `mdl-engine`
- `mdoc-engine`
- `passport-engine`
- `pkd-service`
- `trust-anchor`
- `ui-app`

### Python Wheels

Published as GitHub release artifacts:
- `marty_rs-VERSION-cp311-abi3-manylinux_2_28_x86_64.whl` (from marty-credentials)
- `marty_msf-VERSION-py3-none-any.whl` (from marty-microservices-framework)
- Additional wheels from marty-core sub-crates

## Workflow

### Daily Development

1. **Make changes** to code
2. **Build changed services**:
   ```bash
   make build-push
   ```
3. **Update requirements** if Python packages changed:
   ```bash
   make update-requirements
   ```
4. **Pull latest images** on other machines:
   ```bash
   make pull-all
   ```
5. **Start services**:
   ```bash
   make dev
   ```

### Creating a Release

1. **Ensure all changes are committed**
2. **Create release**:
   ```bash
   make release
   # Enter version when prompted (e.g., 1.2.3)
   ```
3. **Verify release**:
   - Check GitHub releases page for wheels
   - Check GHCR for versioned images

## Troubleshooting

### Authentication Failed

If `docker login ghcr.io` fails:

1. Verify PAT has correct scopes (`write:packages`, `read:packages`)
2. Try authenticating manually:
   ```bash
   echo YOUR_TOKEN | docker login ghcr.io -u YOUR_USERNAME --password-stdin
   ```
3. Check token hasn't expired
4. Create a new token if needed

### Build Failures

**Rust compilation errors:**
```bash
# Update Rust toolchain
rustup update

# Add linux target if missing
rustup target add x86_64-unknown-linux-gnu
```

**Docker build context too large:**
```bash
# Clean up build artifacts
docker system prune -af
```

**Python wheel build fails:**
```bash
# Reinstall maturin
pip install --upgrade maturin

# Check Python version (need 3.11+)
python3 --version
```

### Rate Limiting

GitHub Container Registry has rate limits:
- **Authenticated**: 200 image pulls per hour
- **Unauthenticated**: 100 image pulls per hour

If you hit limits:
1. Wait for the rate limit window to reset
2. Use `--skip-push` to build locally without pushing
3. Consider using registry caching/mirroring

### Incremental Builds Not Working

If builds aren't detecting changes:

```bash
# Force full rebuild
make build-all

# Or manually delete marker
rm .last-build-sha
make build-push
```

### Image Not Found

If `docker-compose` can't find images:

1. Check images exist in GHCR:
   ```bash
   docker image ls | grep ghcr.io
   ```

2. Pull manually:
   ```bash
   docker pull ghcr.io/OWNER/REPO/SERVICE:latest
   ```

3. Verify repository name in GHCR URLs matches your Git remote

## Cost Savings

### Before (GitHub Actions)

- **Cross-platform matrix builds**: ~5-10 hours/month of runner time
- **macOS runners**: $0.08/minute = $24-48/month
- **Ubuntu runners**: $0.008/minute = $2.40-4.80/month
- **Total**: ~$26-53/month for moderate development

### After (Local Builds)

- **GitHub Actions**: Free tier (validation/linting only)
- **GHCR**: Free for public repos
- **GitHub Releases**: Free
- **Total**: $0/month 🎉

Time investment:
- **Initial setup**: ~30 minutes
- **Daily overhead**: ~1-2 minutes (automated)
- **Local build time**: Acceptable (builds run in background)

## Next Steps

1. ✅ Complete initial setup (this guide)
2. 📦 Run first build: `make build-push`
3. 🔄 Update requirements: `make update-requirements`
4. 🚀 Start development: `make dev`
5. 📖 Read the main README for development workflows
6. 🤝 Share setup with team members

## Additional Resources

- [GitHub Container Registry Docs](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Docker Buildx Documentation](https://docs.docker.com/buildx/working-with-buildx/)
- [Maturin User Guide](https://www.maturin.rs/)
- [GitHub CLI Manual](https://cli.github.com/manual/)

## Support

If you encounter issues not covered in this guide:

1. Check `./scripts/build-all-local.sh --help`
2. Review script output for specific errors
3. Check Docker Desktop logs
4. Verify all prerequisites are installed correctly
