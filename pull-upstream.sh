#!/bin/bash
set -e

PATCHES_DIR="/root/cellframe-node/patches"
REPO="/root/cellframe-node"
BUILD_DIR="$REPO/build"

echo "=== Cellframe Node: Pull + Patch + Build ==="
echo ""

# 1. Pull latest upstream
cd "$REPO"
echo "[1/5] Pulling latest from origin (gitlab.demlabs.net)..."
git fetch origin

# Stash parent repo untracked files (patch, scripts, etc)
git stash --include-untracked 2>/dev/null || true

# Reset submodules to clean state before pull
echo "  Resetting submodules to clean state..."
git submodule foreach --recursive 'git checkout -- . 2>/dev/null; git clean -fd 2>/dev/null' || true

git checkout master 2>/dev/null || git checkout $(git rev-parse --abbrev-ref HEAD)
git pull origin master --recurse-submodules || {
    echo "  Pull with submodules had errors, trying without..."
    git pull origin master
}
git submodule update --init --recursive --force || {
    echo "  Warning: some submodules failed to update, continuing..."
}
echo "  Upstream at: $(git log --oneline -1)"

# Pull latest cellframe-sdk master (may be ahead of parent repo's submodule pointer)
echo "  Pulling latest cellframe-sdk..."
cd "$REPO/cellframe-sdk"
git fetch origin
git merge origin/master --no-edit 2>/dev/null && \
    echo "  cellframe-sdk at: $(git log --oneline -1)" || \
    echo "  cellframe-sdk already up to date"
cd "$REPO"

# Restore stashed files (patch, scripts)
git stash pop 2>/dev/null || true

# 2. Tag version with our suffix
echo ""
echo "[2/5] Setting version..."
# Always reset version.mk to upstream first (after stash pop to avoid stash overwriting)
git checkout -- version.mk 2>/dev/null || true
UPSTREAM_PATCH=$(grep VERSION_PATCH version.mk | cut -d= -f2 | tr -d " " | cut -d- -f1)
# If upstream uses LOCALBUILD, use the last known release patch number
if [[ "$UPSTREAM_PATCH" == "LOCALBUILD" ]]; then
    UPSTREAM_PATCH="28"
fi
sed -i "s/^VERSION_PATCH=.*/VERSION_PATCH=${UPSTREAM_PATCH}/" version.mk
echo "  Version: $(grep VERSION_MAJOR version.mk | cut -d= -f2).$(grep VERSION_MINOR version.mk | cut -d= -f2).$(grep VERSION_PATCH version.mk | cut -d= -f2)"

# 3. Apply our patches (individual fix files)
echo ""
echo "[3/5] Applying syncfix patches from $PATCHES_DIR..."
cd "$REPO/cellframe-sdk"
PATCH_FAILED=0
for PATCH in "$PATCHES_DIR"/*.patch; do
    PNAME=$(basename "$PATCH")
    if git apply --check "$PATCH" 2>/dev/null; then
        git apply "$PATCH"
        echo "  [OK] $PNAME"
    elif git apply --3way "$PATCH" 2>/dev/null; then
        echo "  [3WAY] $PNAME (applied with fuzzy match)"
    else
        echo "  [FAIL] $PNAME"
        PATCH_FAILED=1
    fi
done
cd "$REPO"
if [ "$PATCH_FAILED" -eq 1 ]; then
    echo "  WARNING: Some patches failed to apply!"
    echo "  Check output above and manually apply using: /root/cellframe-node/SYNCFIX3_ENHANCEMENT.md"
    read -p "  Continue build anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 3b. Apply inline patches (fixes that cannot be expressed as git patches)
echo ""
echo "[3b/5] Applying inline syncfix patches..."
python3 /root/cellframe-node/inline-patches.py 2>&1 | while read line; do echo "  $line"; done
echo ""

# 4. Build
echo ""
echo "[4/5] Building with Haswell + LTO (Fix 6)..."
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
cmake -DCMAKE_C_FLAGS="-march=haswell -flto=auto -Wno-error=unused-result -Wno-error=address" -DCMAKE_BUILD_TYPE=RelWithDebInfo ..
make -j$(nproc)

# Strip debug symbols
echo "  Stripping binaries..."
strip "$BUILD_DIR/cellframe-node" "$BUILD_DIR/cellframe-node-cli" "$BUILD_DIR/cellframe-node-tool" "$BUILD_DIR/conftool/cellframe-node-config" 2>/dev/null || true

# 5. Package
echo ""
echo "[5/5] Packaging .deb..."
cpack

DEB=$(ls -t cellframe-node*.deb 2>/dev/null | head -1)
if [ -n "$DEB" ]; then
    echo ""
    echo "=== Build complete ==="
    echo "  Package: $BUILD_DIR/$DEB"
    echo ""
    echo "To deploy:"
    echo "  1. Backup current: cp $BUILD_DIR/$DEB /root/cellframe-builds/"
    echo "  2. Install: dpkg -i $BUILD_DIR/$DEB"
else
    echo ""
    echo "=== Build complete (no .deb found, check cpack output) ==="
fi
