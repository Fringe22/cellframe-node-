# ESBOCS Consensus Patches (syncfix3–syncfix6f)

All patches apply to files in the cellframe-sdk submodule.
Combined patch file: `syncfix3-full.patch` (applied by `pull-upstream.sh`)

---

## syncfix3 — Autocollect threshold + session timer (now upstream defaults)

### Fix 3a: Autocollect threshold raised to 10
- **File**: `modules/consensus/esbocs/dap_chain_cs_esbocs.c:423`
- **Change**: `l_objs_count >= 5` → `l_objs_count >= 10`
- **Why**: Reduces unnecessary mempool congestion slowing consensus rounds.
- **Status**: Now upstream default, kept in patch for safety.

### Fix 3b: Session timer interval 1000ms
- **File**: `dap_chain_cs_esbocs.c:680`
- **Status**: Now upstream default.

---

## syncfix4 — DB hash mismatch tolerance

### Fix 4: Tolerate DB hash mismatches before forcing resync
- **File**: `dap_chain_cs_esbocs.c:2477` and `dap_chain_cs_esbocs.h:223`
- **Change**: Added `uint16_t db_hash_mismatch_count` to session struct. Counts
  consecutive mismatches; tolerates up to threshold, then force-recalcs and proceeds.
- **Why**: DB hash desync was blocking SYNC messages entirely, causing missed rounds
  and penalty accumulation. Node now self-heals.

---

## syncfix5 — Penalty kick threshold raised

### Fix 5: PENALTY_KICK 3 → 10
- **File**: `dap_chain_cs_esbocs.h:207`
- **Change**: `#define DAP_CHAIN_ESBOCS_PENALTY_KICK 3U` → `10U`
- **Why**: Validators were kicked too aggressively during transient desyncs.
  10 misses gives time to recover.

---

## syncfix6 — Penalty recovery + mismatch threshold tuning

### Fix 6a: Faster penalty recovery (miss_count -= 2) ✅ KEPT
- **File**: `dap_chain_cs_esbocs.c:2035` in `s_session_validator_mark_online()`
- **Change**: `miss_count--` → `miss_count -= 2` (with bounds check)
- **Why**: With PENALTY_KICK at 10, single decrement was too slow for recovery.
  Halves recovery time.

### Fix 6b: DB hash mismatch threshold 3 → 2 ✅ KEPT
- **File**: `dap_chain_cs_esbocs.c:2477`
- **Change**: `db_hash_mismatch_count <= 3` → `<= 2`
- **Why**: 3 rounds tolerance was too slow — validators missed signing while waiting.
  2 rounds is sufficient to distinguish real desync from transient glitch.

### Fix 6c: Reset penalty on successful round ❌ REVERTED
- **Why reverted**: Modifying miss_count locally after a successful round
  desynchronizes the penalty DB hash with other validators. This caused
  "Different last block hash" errors and RESYNC_CHAINS flapping. The penalty DB
  must remain identical across all validators — any unilateral change breaks
  consensus. Fundamentally incompatible with current ESBOCS design.

---

## Net patches (dap_chain_net.c)

### Patch N1: Stay ONLINE during periodic sync ✅ KEPT
- **File**: `modules/net/dap_chain_net.c`
- **Change**: Removed state drop to `NET_STATE_SYNC_CHAINS` during periodic sync.
  Node stays in `NET_STATE_ONLINE` and syncs in background.
- **Why**: Dropping to SYNC_CHAINS stopped consensus participation during sync windows,
  causing missed rounds and penalty accumulation. Also caused confusing
  `NET_STATE_RESYNC_CHAINS` log messages.

### Patch N2: Smart sync timeout handling ✅ KEPT
- **File**: `modules/net/dap_chain_net.c`
- **Change**: On sync timeout, check atom count before marking error. If local atoms
  match remote count (100%), mark as synced instead of error.
- **Why**: Sync timeouts were triggering unnecessary error states even when the chain
  was fully synced.

### Patch N3: stage_last_activity = 0 ❌ REMOVED
- **Why removed**: Placed in `s_switch_sync_chain()` which runs after every sync
  completion. Flow: sync finishes → ONLINE → activity=0 → timer fires immediately →
  new sync → repeat. Caused infinite sync loop with node stuck in "sync in process".

---

## Build history

| Build | Date | Changes | Status |
|-------|------|---------|--------|
| syncfix3 | Mar 17 | Autocollect + timer | Superseded |
| syncfix4 | Mar 18 | DB hash tolerance | Merged into syncfix5 |
| syncfix5 | Mar 18 | PENALTY_KICK 10 | Superseded |
| syncfix6 | Mar 18 21:17 | +Fix 6a,6b,6c | Fix 6c caused issues |
| syncfix6b | Mar 18 22:42 | Reverted Fix 6b | Investigating |
| syncfix6c | Mar 18 23:09 | Reverted Fix 6c | Net patches missing |
| syncfix6d | Mar 18 23:55 | Re-added Fix 6b | Net patches missing |
| syncfix6e | Mar 19 00:20 | Restored net patches | stage_last_activity bug |
| syncfix6f | Mar 19 02:12 | Removed stage_last_activity | **CURRENT STABLE** |

## syncfix6f — Current stable build

Contains:
- syncfix3: autocollect >= 10, timer 1000ms
- syncfix4: DB hash mismatch tolerance (2 rounds)
- syncfix5: PENALTY_KICK 10
- Fix 6a: faster penalty recovery (miss_count -= 2)
- Fix 6b: mismatch threshold 2
- Net patch N1: stay ONLINE during sync
- Net patch N2: smart timeout handling

Deployed to all 5 nodes (cc12, cc09, cc08, cc20, cc11) on Mar 19, 2026.
Signing rate: ~2.0 blocks/hour (comparable to syncfix5, with cleaner operation).

## Deployment

Built with: `-march=haswell -flto=auto`
Automated build script: `pull-upstream.sh` (pulls upstream, patches, builds, packages)
Builds stored in: `/root/cellframe-builds/`
