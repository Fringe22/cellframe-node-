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

# Snapshot current source state before pulling
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
echo "  Saving source snapshot: cellframe-node-$TIMESTAMP"
cd "$REPO/cellframe-sdk"
PREV_SDK=$(git log --oneline -1 2>/dev/null || echo 'unknown')
cd "$REPO"
PREV_NODE=$(git log --oneline -1 2>/dev/null || echo 'unknown')
echo "  Previous state: node=$PREV_NODE sdk=$PREV_SDK" >> /root/cellframe-builds/build-history.log
echo "  Timestamp: $TIMESTAMP" >> /root/cellframe-builds/build-history.log
echo "---" >> /root/cellframe-builds/build-history.log

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

# 2. Tag version
echo ""
echo "[2/5] Setting version..."
# Use custom version if set, otherwise use upstream
CUSTOM_VERSION="${CELLFRAME_VERSION_PATCH:-}"
git checkout -- version.mk 2>/dev/null || true
UPSTREAM_PATCH=$(grep VERSION_PATCH version.mk | cut -d= -f2 | tr -d " " | cut -d- -f1)
if [[ "$UPSTREAM_PATCH" == "LOCALBUILD" ]]; then
    UPSTREAM_PATCH="28"
fi
if [[ -n "$CUSTOM_VERSION" ]]; then
    sed -i "s/^VERSION_PATCH=.*/VERSION_PATCH=${CUSTOM_VERSION}/" version.mk
    echo "  Version: $(grep VERSION_MAJOR version.mk | cut -d= -f2).$(grep VERSION_MINOR version.mk | cut -d= -f2).${CUSTOM_VERSION} (custom)"
else
    sed -i "s/^VERSION_PATCH=.*/VERSION_PATCH=${UPSTREAM_PATCH}/" version.mk
    echo "  Version: $(grep VERSION_MAJOR version.mk | cut -d= -f2).$(grep VERSION_MINOR version.mk | cut -d= -f2).${UPSTREAM_PATCH} (upstream)"
fi

# 3. Apply all patches (inline - handles conflict resolution, all fixes, and version compat)
echo ""
echo "[3/5] Applying inline syncfix patches..."
python3 /root/cellframe-node/inline-patches.py 2>&1 | while read line; do echo "  $line"; done
PATCH_EXIT=$?
if [ "$PATCH_EXIT" -ne 0 ]; then
    echo "  WARNING: Some inline patches failed! Check output above."
    read -p "  Continue build anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo ""

# Log source state after patches
echo ""
echo "[3c/5] Recording source state..."
{
    echo "Build: $TIMESTAMP"
    echo "  node: $(cd $REPO && git log --oneline -1)"
    echo "  sdk:  $(cd $REPO/cellframe-sdk && git log --oneline -1)"
    echo "  dap:  $(cd $REPO/dap-sdk && git log --oneline -1)"
    echo "  patches: $(ls $PATCHES_DIR/*.patch 2>/dev/null | wc -l) git + $(grep -c 'apply_fix' $REPO/inline-patches.py 2>/dev/null) inline"
} | tee -a /root/cellframe-builds/build-history.log
echo "---" >> /root/cellframe-builds/build-history.log

# 4. Build
echo ""
echo "[4/5] Building with Haswell + LTO (Fix 6)..."
# Backup entire source + build to avoid mixing builds from different source states
BACKUP_DIR="/root/cellframe-node-backup-$(date +%Y%m%d-%H%M%S)"
echo "  Backing up entire source tree to $BACKUP_DIR"
cp -a "$REPO" "$BACKUP_DIR"
echo "  Backup complete ($(du -sh "$BACKUP_DIR" | cut -f1))"
# Clean old build dir for fresh build
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
cmake -DCMAKE_C_FLAGS="-march=haswell -flto=auto -Wno-error=unused-result -Wno-error=address" -DCMAKE_BUILD_TYPE=Release -DCELLFRAME_NO_OPTIMIZATION=OFF ..
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

# 6. Pre-deploy sync check
echo ""
echo "[6/6] Pre-deploy sync check..."
CLI=/opt/cellframe-node/bin/cellframe-node-cli
NODES=(
    "cc-bb|LOCAL|0"
    "cc-bb-12|192.168.2.5|22"
    "cc-bb-14|192.168.2.21|22"
    "node-11|192.168.2.24|22"
    "node-9|192.168.2.25|22"
)

sync_ok=true
for entry in "${NODES[@]}"; do
    IFS="|" read -r name host port <<< "$entry"
    if [ "$host" = "LOCAL" ]; then
        status=$($CLI net -net Backbone get status 2>/dev/null)
    else
        status=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p $port root@$host "$CLI net -net Backbone get status 2>/dev/null" 2>/dev/null)
    fi

    state=$(echo "$status" | grep "current: NET_STATE" | head -1 | awk "{print \$2}")
    pct=$(echo "$status" | grep "percent:" | tail -1 | grep -oP "[\d.]+" | head -1)

    if [ "$state" != "NET_STATE_ONLINE" ]; then
        echo "  W $name: $state (NOT ONLINE)"
        sync_ok=false
    elif [ -n "$pct" ] && [ "$(echo "$pct < 99.9" | bc -l 2>/dev/null)" = "1" ]; then
        echo "  W $name: ONLINE but sync at ${pct}%"
        sync_ok=false
    else
        echo "  OK $name: ONLINE, synced"
    fi
done

if [ "$sync_ok" = false ]; then
    echo ""
    echo "  WARNING: Not all nodes are fully synced!"
    echo "  Deploying now may cause chain desync on lagging nodes."
    echo "  Wait for all nodes to reach ONLINE + 100% before running dpkg -i"
else
    echo ""
    echo "  All nodes synced and ready for deploy."
fi
