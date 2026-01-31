# Zero-Cost CI Quick Reference

## 🚀 Initial Setup (One-Time)

```bash
# 1. Install tools
brew install gh docker
pip install maturin build twine

# 2. Setup GHCR authentication
make setup
# (Enter GitHub username and PAT when prompted)
```

## 📦 Daily Workflow

```bash
# Build and push changed services
make build-push

# Update Python requirements
make update-requirements

# Start development environment
make dev
```

## 🎯 Common Commands

| Command | Description | Time |
|---------|-------------|------|
| `make setup` | GHCR authentication (one-time) | 2 min |
| `make build-push` | Build & push changed artifacts | 10-30 min |
| `make build-all` | Force rebuild everything | 30-60 min |
| `make pull-all` | Pull latest images | 2 min |
| `make update-requirements` | Update Python packages | 1 min |
| `make release` | Create semantic version | 60+ min |

## 🔧 Troubleshooting

### Authentication failed
```bash
# Re-run setup
make setup
```

### Force full rebuild
```bash
rm .last-build-sha
make build-push
```

### Build without pushing
```bash
./scripts/build-all-local.sh --skip-push
```

### Check what will be built
```bash
git diff $(cat .last-build-sha) HEAD --name-only
```

## 📝 Files Created

- `scripts/build-all-local.sh` - Main build script
- `scripts/ghcr-setup.sh` - Authentication helper  
- `scripts/release-helper.sh` - Release automation
- `scripts/update-requirements.sh` - Update Python deps
- `docs/LOCAL_BUILD_SETUP.md` - Full documentation
- `ZERO_COST_CI_IMPLEMENTATION.md` - Implementation summary

## 💰 Cost Savings

- **Before**: $26-53/month (GitHub Actions)
- **After**: $0/month (local builds)
- **Savings**: 100%

## 📚 Documentation

- Full setup: `docs/LOCAL_BUILD_SETUP.md`
- Implementation details: `ZERO_COST_CI_IMPLEMENTATION.md`
- Script help: `./scripts/build-all-local.sh --help`
- Make targets: `make help`

## 🏗️ What Gets Built

**10 Docker Images:**
csca-service, document-signer, dtc-engine, inspection-system,
mdl-engine, mdoc-engine, passport-engine, pkd-service,
trust-anchor, ui-app

**3 Python Wheels:**
marty-rs, marty-msf, marty-common

## ⚡ Quick Test

```bash
# 1. Setup (if not done)
make setup

# 2. Build (first time will take 30-60 min)
make build-push

# 3. Verify
docker image ls | grep ghcr.io

# 4. Check GitHub releases
gh release list
```

## 🎓 Next Steps

1. ✅ Read `docs/LOCAL_BUILD_SETUP.md`
2. ✅ Run `make setup`
3. ✅ Run `make build-push`
4. ✅ Verify artifacts in GHCR
5. ✅ Update team on new workflow
