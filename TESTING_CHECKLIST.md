# Testing Checklist for Zero-Cost CI Implementation

Use this checklist to validate the implementation works correctly.

## ✅ Pre-Flight Checks

### Prerequisites
- [ ] Docker Desktop installed and running
- [ ] Rust toolchain installed (`rustc --version`)
- [ ] Python 3.11+ installed (`python3 --version`)
- [ ] GitHub CLI installed (`gh --version`)
- [ ] gh CLI authenticated (`gh auth status`)
- [ ] maturin installed (`pip list | grep maturin`)
- [ ] build tools installed (`pip list | grep build`)

### Repository State
- [ ] On correct branch (main/develop)
- [ ] No uncommitted changes
- [ ] Git remote is correct (`git remote -v`)
- [ ] Can access GHCR repository

## 🔐 Authentication Test

### GHCR Setup
```bash
cd /Volumes/Heart\ of\ Gold/Github/work/Marty
make setup
```

- [ ] Script prompts for GitHub username
- [ ] Script prompts for PAT token
- [ ] Login succeeds
- [ ] Credentials stored
- [ ] `docker info | grep ghcr.io` shows GHCR

### Validation
```bash
# Should work without password prompt
docker pull ghcr.io/docker/welcome-to-docker:latest
```

- [ ] Pull succeeds without authentication prompt

## 🔨 Build System Test

### Initial Build (Full)
```bash
# This will take 30-60 minutes
make build-all
```

**Watch for:**
- [ ] Prerequisites check passes
- [ ] Python wheel building starts
- [ ] marty-credentials builds
- [ ] marty-core builds
- [ ] marty-msf builds
- [ ] GitHub release created
- [ ] Docker images start building
- [ ] All 10 services build
- [ ] Images tagged correctly
- [ ] Push to GHCR succeeds
- [ ] `.last-build-sha` file created
- [ ] Build completes without errors

**Verify artifacts:**
```bash
# Check local images
docker image ls | grep ghcr.io

# Check GitHub releases
gh release list

# Check GHCR
gh api /user/packages/container
```

- [ ] 10 Docker images present locally
- [ ] Images have both `latest` and `dev-*` tags
- [ ] GitHub release created with wheels
- [ ] Wheels are downloadable

### Incremental Build Test

**Make a small change:**
```bash
# Edit a file in one service
echo "# Test change" >> docker/ui-app.Dockerfile
git add docker/ui-app.Dockerfile
git commit -m "test: incremental build"
```

**Build again:**
```bash
make build-push
```

**Verify:**
- [ ] Only changed service rebuilds
- [ ] Other services skipped
- [ ] Build time < 10 minutes
- [ ] New dev tag created
- [ ] `.last-build-sha` updated

**Revert test change:**
```bash
git reset --hard HEAD~1
```

### Force Rebuild Test
```bash
make build-all
```

- [ ] All services rebuild regardless of changes
- [ ] Build completes successfully

### Skip Options Test

**Skip wheels:**
```bash
./scripts/build-all-local.sh --skip-wheels
```
- [ ] Docker images build
- [ ] Wheels skipped
- [ ] No GitHub release created

**Skip Docker:**
```bash
./scripts/build-all-local.sh --skip-docker
```
- [ ] Wheels build
- [ ] Docker images skipped

**Skip push:**
```bash
./scripts/build-all-local.sh --skip-push
```
- [ ] Everything builds locally
- [ ] Nothing pushed to GHCR
- [ ] No GitHub release

## 📦 Python Packages Test

### Update Requirements
```bash
make update-requirements
```

**Verify:**
- [ ] Script finds latest release
- [ ] Wheel URLs generated
- [ ] requirements.txt updated
- [ ] Backup created
- [ ] URLs are accessible

**Test URLs:**
```bash
# Pick one URL from requirements.txt and try to download
curl -L -I "URL_FROM_REQUIREMENTS"
```
- [ ] URL returns 200 OK
- [ ] File size is reasonable

### Install Test
```bash
cd ../marty-ui
pip install -r src/requirements.txt
```

- [ ] Wheels download successfully
- [ ] Installation completes
- [ ] No errors

## 🚀 Release Test

### Semantic Release
```bash
# Create a test release
make release
# Enter version: 0.0.1-test
```

**Verify:**
- [ ] Prompts for version
- [ ] Updates pyproject.toml files
- [ ] Updates Cargo.toml files
- [ ] Creates git tag
- [ ] Prompts to push tag
- [ ] Full rebuild happens
- [ ] Images tagged with version
- [ ] Push succeeds

**Cleanup test release:**
```bash
git tag -d v0.0.1-test
git reset --hard HEAD~1
```

## 🔄 Pull Test

### Pull All Images
```bash
# On a different machine or after `docker system prune -a`
make pull-all
```

**Verify:**
- [ ] All 10 services pull
- [ ] Images have `latest` tag
- [ ] No authentication errors
- [ ] Pull completes quickly

### Start Services
```bash
make dev
```

- [ ] Services start successfully
- [ ] UI accessible at http://localhost:9080
- [ ] API accessible at http://localhost:8000
- [ ] No build happens (uses pulled images)

## 🧪 CI Workflow Test

### Validation Only
```bash
# Push a commit to trigger CI
git commit --allow-empty -m "test: CI validation"
git push
```

**Check GitHub Actions:**
- [ ] Workflow runs
- [ ] Only linting/validation runs
- [ ] No builds happen
- [ ] Completes in < 5 minutes
- [ ] No cost incurred

## 📚 Documentation Test

### Check Documentation
- [ ] [docs/LOCAL_BUILD_SETUP.md](./docs/LOCAL_BUILD_SETUP.md) exists
- [ ] [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) exists
- [ ] [ZERO_COST_CI_IMPLEMENTATION.md](./ZERO_COST_CI_IMPLEMENTATION.md) exists
- [ ] README.md updated with build section
- [ ] All links work

### Help Commands
```bash
./scripts/build-all-local.sh --help
./scripts/ghcr-setup.sh
./scripts/release-helper.sh --help
./scripts/update-requirements.sh --help
make help
```

- [ ] All help messages display correctly
- [ ] Instructions are clear
- [ ] Options documented

## 🔍 Edge Cases

### No Changes Build
```bash
# Build twice without changes
make build-push
make build-push
```

- [ ] Second build skips everything
- [ ] "No changes" messages shown
- [ ] Completes quickly

### Build Failure Recovery
```bash
# Introduce a syntax error
echo "INVALID SYNTAX" >> docker/ui-app.Dockerfile
make build-push
```

- [ ] Build fails gracefully
- [ ] Error message is clear
- [ ] `.last-build-sha` not updated
- [ ] Can retry after fix

**Fix and retry:**
```bash
git checkout docker/ui-app.Dockerfile
make build-push
```

- [ ] Build succeeds after fix

### Network Failure
```bash
# Disable network and try to push
# (Don't actually do this, just verify error handling)
```

- [ ] Push failures are reported
- [ ] Script doesn't crash
- [ ] Can retry when network is back

## 🎯 Performance Tests

### Build Time Tracking
Record times for:

**Full Build:**
- Python wheels: ______ minutes
- Docker images: ______ minutes
- Total: ______ minutes
- Target: < 60 minutes

**Incremental Build (1 service changed):**
- Time: ______ minutes
- Target: < 10 minutes

**Pull All:**
- Time: ______ minutes
- Target: < 5 minutes

## ✨ Final Validation

### Complete Workflow Test

**Day 1:**
```bash
# Fresh setup
make setup
make build-push
make dev
```

**Day 2:**
```bash
# Make changes
git commit -m "feat: new feature"
make build-push
make update-requirements
make dev
```

**Release Day:**
```bash
make release
# Enter version: 1.0.0
```

**All steps:**
- [ ] Setup works smoothly
- [ ] Builds succeed
- [ ] Artifacts distributed
- [ ] Services run correctly
- [ ] Release process clean
- [ ] Zero GitHub Actions costs

## 📊 Success Criteria

- [ ] All prerequisite tools installed
- [ ] GHCR authentication works
- [ ] Full build completes successfully
- [ ] Incremental builds work correctly
- [ ] Python packages distributed via GitHub Releases
- [ ] Docker images in GHCR
- [ ] Requirements update works
- [ ] Pull and run works
- [ ] Release process tested
- [ ] CI validation-only runs
- [ ] Documentation complete and accurate
- [ ] Zero GitHub Actions charges

## 🚨 Known Issues

Document any issues found during testing:

1. 
2. 
3. 

## 📝 Notes

Additional observations:

-
-
-

## ✅ Sign-Off

- [ ] All tests passed
- [ ] Documentation reviewed
- [ ] Team trained
- [ ] Ready for production use

**Tested by:** _______________
**Date:** _______________
**Version:** _______________
