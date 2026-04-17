#!/usr/bin/env python3
"""Inline patches for cellframe-node that cannot be expressed as git diff patches.
These modify the source directly after git patches are applied."""

import sys
import os

REPO = "/root/cellframe-node"
ESBOCS_C = f"{REPO}/cellframe-sdk/modules/consensus/esbocs/dap_chain_cs_esbocs.c"
ESBOCS_H = f"{REPO}/cellframe-sdk/modules/consensus/esbocs/include/dap_chain_cs_esbocs.h"
NET_C = f"{REPO}/cellframe-sdk/modules/net/dap_chain_net.c"

def resolve_merge_conflicts():
    """Auto-resolve git merge conflicts left by SDK merge + git patches."""
    # Scan all .c and .h files in the SDK for conflicts
    import glob
    files = glob.glob(f"{REPO}/cellframe-sdk/modules/**/*.[ch]", recursive=True)
    files += glob.glob(f"{REPO}/cellframe-sdk/modules/**/*.h", recursive=True)
    resolved = 0
    for fpath in files:
        if not os.path.exists(fpath):
            continue
        with open(fpath, 'r') as f:
            txt = f.read()
        if '<<<<<<<' not in txt:
            continue

        lines = txt.split('\n')
        new_lines = []
        in_ours = False
        in_theirs = False
        ours_block = []
        theirs_block = []

        for line in lines:
            if line.startswith('<<<<<<<'):
                in_ours = True
                ours_block = []
                continue
            elif line.startswith('=======') and in_ours:
                in_ours = False
                in_theirs = True
                theirs_block = []
                continue
            elif line.startswith('>>>>>>>') and in_theirs:
                in_theirs = False
                # If theirs has our syncfix patches, keep struct defs from ours + patched values from theirs
                # Otherwise just keep upstream (ours) for files we don't patch
                has_syncfix = any('syncfix' in t for t in theirs_block)
                if has_syncfix:
                    for ol in ours_block:
                        skip = False
                        if 'PENALTY_KICK' in ol and any('PENALTY_KICK' in t for t in theirs_block):
                            skip = True
                        if 'NET_STATE_SYNC_CHAINS' in ol and 'syncfix' not in ol:
                            skip = True
                        if 's_net_states_proc' in ol and any('syncfix' in t for t in theirs_block):
                            skip = True
                        if not skip:
                            new_lines.append(ol)
                    for tl in theirs_block:
                        new_lines.append(tl)
                else:
                    # For non-patched conflicts: keep origin/master (theirs) as it's the newer code
                    for tl in theirs_block:
                        new_lines.append(tl)
                continue

            if in_ours:
                ours_block.append(line)
            elif in_theirs:
                theirs_block.append(line)
            else:
                new_lines.append(line)

        with open(fpath, 'w') as f:
            f.write('\n'.join(new_lines))
        fname = os.path.basename(fpath)
        print(f"[CONFLICT-RESOLVED] {fname}")
        resolved += 1

    # Deduplicate db_hash_mismatch_count field
    if os.path.exists(ESBOCS_H):
        with open(ESBOCS_H, 'r') as f:
            hlines = f.readlines()
        seen_dbhash = False
        deduped = []
        for l in hlines:
            if 'db_hash_mismatch_count' in l:
                if seen_dbhash:
                    continue
                seen_dbhash = True
            deduped.append(l)
        if len(deduped) < len(hlines):
            with open(ESBOCS_H, 'w') as f:
                f.writelines(deduped)
            print("[DEDUP] db_hash_mismatch_count")

    if resolved == 0:
        print("[CLEAN] No merge conflicts found")

# Step 0: Resolve any merge conflicts before applying patches
resolve_merge_conflicts()

def apply_fix(filepath, old, new, name):
    with open(filepath, "r") as f:
        content = f.read()
    if new in content:
        print(f"[SKIP] {name} (already applied)")
        return True
    if old not in content:
        print(f"[FAIL] {name} (target not found)")
        return False
    content = content.replace(old, new)
    with open(filepath, "w") as f:
        f.write(content)
    print(f"[OK] {name}")
    return True

ok = 0
fail = 0

# Fix 02: Don't mark ERROR on sync timeout if chain is 100% synced (legacy timeout path)
r = apply_fix(NET_C,
    """        } else if (l_now - l_net_pvt->sync_context.stage_last_activity > l_net_pvt->sync_context.sync_activity_timeout) {
            log_it(L_WARNING, "Chain %s of net %s sync activity timeout", l_chain->name, l_net->pub.name);
            l_state_forming = CHAIN_SYNC_STATE_ERROR;
            l_restart_reason = DAP_CHAIN_NET_SYNC_RESTART_REASON_ACTIVITY_TIMEOUT;
            s_sync_diag_counter_inc(&l_net_pvt->sync_context.diag_timeout_liveness_count);
        }""",
    """        } else if (l_now - l_net_pvt->sync_context.stage_last_activity > l_net_pvt->sync_context.sync_activity_timeout) {
            // syncfix3-fix2: Check if chain is actually 100% synced before marking ERROR
            uint64_t l_local_atoms = l_chain->callback_count_atom(l_chain);
            if (l_chain->atom_num_last > 0 && l_local_atoms >= l_chain->atom_num_last) {
                log_it(L_INFO, "syncfix3: Chain %s of net %s sync timeout but 100%% synced, marking synced",
                               l_chain->name, l_net->pub.name);
                l_state_forming = CHAIN_SYNC_STATE_SYNCED;
                l_chain->state = CHAIN_SYNC_STATE_SYNCED;
            } else {
                log_it(L_WARNING, "Chain %s of net %s sync activity timeout", l_chain->name, l_net->pub.name);
                l_state_forming = CHAIN_SYNC_STATE_ERROR;
                l_restart_reason = DAP_CHAIN_NET_SYNC_RESTART_REASON_ACTIVITY_TIMEOUT;
                s_sync_diag_counter_inc(&l_net_pvt->sync_context.diag_timeout_liveness_count);
            }
        }""",
    "Fix 02: sync-timeout-check-synced (legacy path)")
ok += r; fail += not r

# Fix 02b: Same for split-timeout liveness path
r = apply_fix(NET_C,
    """            if (l_now - l_net_pvt->sync_context.last_rx_activity > l_net_pvt->sync_context.sync_activity_timeout) {
                // check if need restart sync chains (emergency mode)
                log_it(L_WARNING, "Chain %s of net %s sync liveness timeout", l_chain->name, l_net->pub.name);
                l_state_forming = CHAIN_SYNC_STATE_ERROR;
                l_restart_reason = DAP_CHAIN_NET_SYNC_RESTART_REASON_ACTIVITY_TIMEOUT;
                s_sync_diag_counter_inc(&l_net_pvt->sync_context.diag_timeout_liveness_count);""",
    """            if (l_now - l_net_pvt->sync_context.last_rx_activity > l_net_pvt->sync_context.sync_activity_timeout) {
                // syncfix3-fix2: Check if chain is actually synced before marking ERROR
                uint64_t l_local_atoms_lv = l_chain->callback_count_atom(l_chain);
                if (l_chain->atom_num_last > 0 && l_local_atoms_lv >= l_chain->atom_num_last) {
                    log_it(L_INFO, "syncfix3: Chain %s of net %s liveness timeout but 100%% synced", l_chain->name, l_net->pub.name);
                    l_state_forming = CHAIN_SYNC_STATE_SYNCED;
                    l_chain->state = CHAIN_SYNC_STATE_SYNCED;
                } else {
                    log_it(L_WARNING, "Chain %s of net %s sync liveness timeout", l_chain->name, l_net->pub.name);
                    l_state_forming = CHAIN_SYNC_STATE_ERROR;
                    l_restart_reason = DAP_CHAIN_NET_SYNC_RESTART_REASON_ACTIVITY_TIMEOUT;
                    s_sync_diag_counter_inc(&l_net_pvt->sync_context.diag_timeout_liveness_count);
                }""",
    "Fix 02b: sync-timeout-check-synced (liveness path)")
ok += r; fail += not r

# Fix 02c: Same for split-timeout progress path
r = apply_fix(NET_C,
    """            } else if (l_now - l_net_pvt->sync_context.last_progress_activity > l_net_pvt->sync_context.sync_progress_timeout) {
                log_it(L_WARNING, "Chain %s of net %s sync progress timeout", l_chain->name, l_net->pub.name);
                l_state_forming = CHAIN_SYNC_STATE_ERROR;
                l_restart_reason = DAP_CHAIN_NET_SYNC_RESTART_REASON_PROGRESS_TIMEOUT;
                s_sync_diag_counter_inc(&l_net_pvt->sync_context.diag_timeout_progress_count);""",
    """            } else if (l_now - l_net_pvt->sync_context.last_progress_activity > l_net_pvt->sync_context.sync_progress_timeout) {
                uint64_t l_local_atoms_pg = l_chain->callback_count_atom(l_chain);
                if (l_chain->atom_num_last > 0 && l_local_atoms_pg >= l_chain->atom_num_last) {
                    log_it(L_INFO, "syncfix3: Chain %s of net %s progress timeout but 100%% synced", l_chain->name, l_net->pub.name);
                    l_state_forming = CHAIN_SYNC_STATE_SYNCED;
                    l_chain->state = CHAIN_SYNC_STATE_SYNCED;
                } else {
                    log_it(L_WARNING, "Chain %s of net %s sync progress timeout", l_chain->name, l_net->pub.name);
                    l_state_forming = CHAIN_SYNC_STATE_ERROR;
                    l_restart_reason = DAP_CHAIN_NET_SYNC_RESTART_REASON_PROGRESS_TIMEOUT;
                    s_sync_diag_counter_inc(&l_net_pvt->sync_context.diag_timeout_progress_count);
                }""",
    "Fix 02c: sync-timeout-check-synced (progress path)")
ok += r; fail += not r

# Fix 06-header: Add db_hash_mismatch_count field to session struct
# Skip if already added by git patch 06 (which uses syncfix3-fix8 comment)
with open(ESBOCS_H, "r") as _f:
    _h = _f.read()
if "db_hash_mismatch_count" in _h:
    print("[SKIP] Fix 06-header: db_hash_mismatch_count field (already present)")
else:
    r = apply_fix(ESBOCS_H,
        "    bool cs_timer, round_fast_forward, sync_failed, new_round_enqueued, is_actual_hash;",
        "    uint16_t db_hash_mismatch_count; // syncfix3-fix6: track consecutive DB hash mismatches\n    bool cs_timer, round_fast_forward, sync_failed, new_round_enqueued, is_actual_hash;",
        "Fix 06-header: db_hash_mismatch_count field")
    ok += r; fail += not r

# Fix 01: Stay ONLINE during sync - prevent SYNC_CHAINS drop
r = apply_fix(NET_C,
    """        if (l_net_pvt->state == NET_STATE_ONLINE) {
            if (l_now - l_resync_anchor <= l_net_pvt->sync_context.sync_idle_time)
                return;
            l_net_pvt->state = NET_STATE_SYNC_CHAINS;
            s_net_states_proc(l_net);
            l_restart_reason = DAP_CHAIN_NET_SYNC_RESTART_REASON_PROGRESS_TIMEOUT;
        }""",
    """        if (l_net_pvt->state == NET_STATE_ONLINE) {
            if (l_now - l_resync_anchor <= l_net_pvt->sync_context.sync_idle_time)
                return;
            // syncfix3-fix1: Stay ONLINE while syncing - do not drop state to SYNC_CHAINS
            // This allows consensus participation during periodic sync
            l_restart_reason = DAP_CHAIN_NET_SYNC_RESTART_REASON_PROGRESS_TIMEOUT;
        }""",
    "Fix 01: stay-online-during-sync")
ok += r; fail += not r

# Fix 05: Consensus message priority HIGH (two locations)
r = apply_fix(ESBOCS_C,
    "dap_proc_thread_callback_add(l_session->proc_thread, s_process_incoming_message, l_args)",
    "dap_proc_thread_callback_add_pri(l_session->proc_thread, s_process_incoming_message, l_args, DAP_QUEUE_MSG_PRIORITY_HIGH)",
    "Fix 05a: consensus-msg-priority (l_session)")
ok += r; fail += not r

r = apply_fix(ESBOCS_C,
    "dap_proc_thread_callback_add(a_session->proc_thread, s_process_incoming_message, l_args)",
    "dap_proc_thread_callback_add_pri(a_session->proc_thread, s_process_incoming_message, l_args, DAP_QUEUE_MSG_PRIORITY_HIGH)",
    "Fix 05b: consensus-msg-priority (a_session)")
ok += r; fail += not r

# Fix 06: DB hash mismatch tolerance
r = apply_fix(ESBOCS_C,
    """            debug_if(l_cs_debug, L_MSG, "net:%s, chain:%s, round:%"DAP_UINT64_FORMAT_U", sync_attempt %"DAP_UINT64_FORMAT_U
                                        " SYNC message is rejected cause DB hash mismatch",
                                           l_session->chain->net_name, l_session->chain->name, l_session->cur_round.id,
                                               l_session->cur_round.sync_attempt);
            break;""",
    """            l_session->db_hash_mismatch_count++;
            if (l_session->db_hash_mismatch_count <= 2) {
                l_session->is_actual_hash = false;
                debug_if(l_cs_debug, L_MSG, "net:%s, chain:%s, round:%"DAP_UINT64_FORMAT_U", sync_attempt %"DAP_UINT64_FORMAT_U
                                            " SYNC rejected: DB hash mismatch (count %u/2, will recalc next round)",
                                               l_session->chain->net_name, l_session->chain->name, l_session->cur_round.id,
                                                   l_session->cur_round.sync_attempt, l_session->db_hash_mismatch_count);
                break;
            }
            // syncfix3-fix6: After 3 consecutive mismatches, force recalc and proceed anyway
            l_session->is_actual_hash = false;
            s_db_calc_sync_hash(l_session);
            l_session->db_hash_mismatch_count = 0;
            log_it(L_WARNING, "net:%s, chain:%s, round:%"DAP_UINT64_FORMAT_U", sync_attempt %"DAP_UINT64_FORMAT_U
                              " DB hash mismatch persisted 2+ rounds, proceeding (penalty DB will resync)",
                                 l_session->chain->net_name, l_session->chain->name, l_session->cur_round.id,
                                     l_session->cur_round.sync_attempt);""",
    "Fix 06: dbhash-tolerance")
ok += r; fail += not r

# REMOVED: # Fix 10: Rollback log level
# REMOVED: r = apply_fix(ESBOCS_C,
# REMOVED:     'L_ERROR, "No previous state registered',
# REMOVED:     'L_DEBUG, "No previous state registered',
# REMOVED:     "Fix 10: rollback-log-level")
# REMOVED: ok += r; fail += not r

# Fix 11: listen_ensure = 1
r = apply_fix(ESBOCS_C,
    "a_session->listen_ensure = 0;",
    "a_session->listen_ensure = 1; // syncfix: was 0, caused zero timeout on first attempt",
    "Fix 11: listen-ensure-init")
ok += r; fail += not r

# Fix 12: Default to LEGACY protocol for unknown peers
r = apply_fix(ESBOCS_C,
    """    return s_protocol_version_is_supported(a_unknown_peer_version) ?
            a_unknown_peer_version : DAP_CHAIN_ESBOCS_PROTOCOL_VERSION_CURRENT;""",
    """    // syncfix-fix12: Default to LEGACY when peer version unknown for backward compatibility
    return DAP_CHAIN_ESBOCS_PROTOCOL_VERSION_LEGACY;""",
    "Fix 12: version-send-legacy")
ok += r; fail += not r

# Fix 13: Accept protocol version 0 from old nodes (ROOT CAUSE)
r = apply_fix(ESBOCS_C,
    """    return a_version == DAP_CHAIN_ESBOCS_PROTOCOL_VERSION_LEGACY ||
            a_version == DAP_CHAIN_ESBOCS_PROTOCOL_VERSION_CURRENT;""",
    """    // syncfix-fix13: accept version 0 from old nodes that do not set version field
    return a_version == 0 ||
            a_version == DAP_CHAIN_ESBOCS_PROTOCOL_VERSION_LEGACY ||
            a_version == DAP_CHAIN_ESBOCS_PROTOCOL_VERSION_CURRENT;""",
    "Fix 13: version-accept-zero (ROOT CAUSE FIX)")
ok += r; fail += not r

# REMOVED: # Fix 08: Penalty kick threshold = 10 (check header file, not .c)
# REMOVED: ESBOCS_H = f"{REPO}/cellframe-sdk/modules/consensus/esbocs/include/dap_chain_cs_esbocs.h"
# REMOVED: r = apply_fix(ESBOCS_H,
# REMOVED:     "#define DAP_CHAIN_ESBOCS_PENALTY_KICK   3U",
# REMOVED:     "#define DAP_CHAIN_ESBOCS_PENALTY_KICK   10U      // syncfix3-fix8: raised from 3 to reduce false kicks",
# REMOVED:     "Fix 08: penalty-kick-10")
# REMOVED: ok += r; fail += not r

# Fix 03: Force immediate sync on ONLINE transition
r = apply_fix(NET_C,
    """    l_net_pvt->state = NET_STATE_ONLINE;
    l_net_pvt->was_online = true;  // Mark that network has reached ONLINE state
    l_net_pvt->sync_context.last_progress_activity = dap_time_now();""",
    """    l_net_pvt->state = NET_STATE_ONLINE;
    l_net_pvt->was_online = true;  // Mark that network has reached ONLINE state
    // syncfix3-fix3: Force immediate sync on ONLINE transition to catch up on missed blocks
    l_net_pvt->sync_context.stage_last_activity = 0;
    l_net_pvt->sync_context.last_progress_activity = dap_time_now();""",
    "Fix 03: immediate-sync-on-online")
ok += r; fail += not r

# Fix 07: Register DB change notifier for penalty group (invalidates cached hash on async changes)
# Upstream removed this in Aug 2024 ("DB last hash calculation fix") but the on-demand recalc
# misses async penalty DB changes from cluster sync, causing persistent hash mismatch after restart.
# We keep penalty_clear_on_start logic intact (defaults to false = no erase), just add the notifier.
r = apply_fix(ESBOCS_C,
    """    dap_link_manager_add_net_associate(l_net->pub.id.uint64, l_session->db_cluster->links_cluster);
    if (dap_config_get_item_bool_default(a_chain_net_cfg, DAP_CHAIN_ESBOCS_CS_TYPE_STR, "penalty_clear_on_start", false))
        dap_global_db_erase_table_sync(l_sync_group);
    DAP_DELETE(l_sync_group);""",
    """    dap_link_manager_add_net_associate(l_net->pub.id.uint64, l_session->db_cluster->links_cluster);
    dap_global_db_cluster_add_notify_callback(l_session->db_cluster, s_db_change_notifier, l_session); // syncfix7: invalidate hash on async DB changes
    if (dap_config_get_item_bool_default(a_chain_net_cfg, DAP_CHAIN_ESBOCS_CS_TYPE_STR, "penalty_clear_on_start", false))
        dap_global_db_erase_table_sync(l_sync_group);
    DAP_DELETE(l_sync_group);""",
    "Fix 07: db-change-notifier-register")
ok += r; fail += not r

# Fix 07b: Implement s_db_change_notifier function body (forward decl exists in upstream)
r = apply_fix(ESBOCS_C,
    "int dap_chain_esbocs_set_empty_block_every_times(dap_chain_t *a_chain, uint16_t a_blockgen_period)",
    """// syncfix7: DB change notifier for penalty group (invalidates cached hash on async changes)
static void s_db_change_notifier(dap_store_obj_t *a_obj, void *a_arg)
{
    dap_chain_esbocs_session_t *l_session = (dap_chain_esbocs_session_t *)a_arg;
    if (l_session) {
        l_session->is_actual_hash = false;
        log_it(L_DEBUG, "syncfix7: DB change notifier fired, invalidated hash for session %p", l_session);
    }
}

int dap_chain_esbocs_set_empty_block_every_times(dap_chain_t *a_chain, uint16_t a_blockgen_period)""",
    "Fix 07b: db-change-notifier-impl")
ok += r; fail += not r

# Fix 14: DISABLED - our nodes are minority, causes hash mismatch with unpatched majority
# Deterministic sign assembly - remove attempt-dependent primary validator reordering
# ROOT CAUSE of different final hash of local and remote validators blocking all Backbone blocks
r = True  # SKIP Fix 14
if False:  # noqa
 r_disabled = apply_fix(ESBOCS_C,
    '''        l_store->candidate_signs = dap_list_sort(l_store->candidate_signs, s_signs_sort_callback);
        size_t l_candidate_size_exclude_signs = l_store->candidate_size;
        for (dap_list_t *it = l_store->candidate_signs; it; it = it->next) {
            dap_sign_t *l_candidate_sign = (dap_sign_t *)it->data;
            size_t l_candidate_sign_size = dap_sign_get_size(l_candidate_sign);
            dap_chain_addr_t l_signing_addr_cur;
            dap_chain_addr_fill_from_sign(&l_signing_addr_cur, l_candidate_sign, a_session->chain->net_id);
            dap_chain_block_t *l_signed_candidate = DAP_REALLOC_RET_IF_FAIL(l_store->candidate, l_store->candidate_size + l_candidate_sign_size);
            l_store->candidate = l_signed_candidate;
            if (dap_chain_addr_compare(&l_signing_addr_cur, &a_session->cur_round.attempt_submit_validator) &&
                                       l_store->candidate_size != l_candidate_size_exclude_signs) {
                // If it's the primary attempt validator sign, place it in the beginnig
                if (l_store->candidate_size > l_candidate_size_exclude_signs)
                    memmove((byte_t *)l_store->candidate + l_candidate_size_exclude_signs + l_candidate_sign_size,
                            (byte_t *)l_store->candidate + l_candidate_size_exclude_signs,
                            l_store->candidate_size - l_candidate_size_exclude_signs);
                memcpy((byte_t *)l_store->candidate + l_candidate_size_exclude_signs, l_candidate_sign, l_candidate_sign_size);
            } else
                memcpy(((byte_t *)l_store->candidate) + l_store->candidate_size, l_candidate_sign, l_candidate_sign_size);
            l_store->candidate_size += l_candidate_sign_size;
        }''',
    '''        l_store->candidate_signs = dap_list_sort(l_store->candidate_signs, s_signs_sort_callback);
        /* syncfix-fix14: Use pure sorted order for sign assembly. Do NOT reorder
         * by the attempt's primary validator (attempt_submit_validator), because
         * that makes precommit_candidate_hash attempt-dependent. When nodes are
         * on different attempts (common during sync desync), their precommit
         * hashes diverge causing different final hash failures and zero block
         * production. Pure sorted order is attempt-independent. */
        for (dap_list_t *it = l_store->candidate_signs; it; it = it->next) {
            dap_sign_t *l_candidate_sign = (dap_sign_t *)it->data;
            size_t l_candidate_sign_size = dap_sign_get_size(l_candidate_sign);
            dap_chain_block_t *l_signed_candidate = DAP_REALLOC_RET_IF_FAIL(l_store->candidate, l_store->candidate_size + l_candidate_sign_size);
            l_store->candidate = l_signed_candidate;
            memcpy(((byte_t *)l_store->candidate) + l_store->candidate_size, l_candidate_sign, l_candidate_sign_size);
            l_store->candidate_size += l_candidate_sign_size;
        }''',
    "Fix 14: deterministic-sign-assembly (FINALHASH ROOT CAUSE)")
# ok += r; fail += not r  # Fix 14 disabled

# REMOVED: # Fix 04: Lower autocollect threshold from 10 to 0 (collect any pending rewards)
# REMOVED: r = apply_fix(ESBOCS_C,
# REMOVED:     "if (l_objs_count >= 10) {",
# REMOVED:     "if (l_objs_count > 0) { // syncfix3-fix4: lower autocollect threshold",
# REMOVED:     "Fix 04: autocollect-threshold")
# REMOVED: ok += r; fail += not r

# REMOVED: # Fix 09: Miss count decrement comment (cosmetic, confirms decrement-by-1 behavior)
# REMOVED: r = apply_fix(ESBOCS_C,
# REMOVED:     "        if (l_item->miss_count)\n            l_item->miss_count--;",
# REMOVED:     "        if (l_item->miss_count)\n            l_item->miss_count--;  // syncfix3-fix9: match network decrement-by-1 (Fix 6a reverted)",
# REMOVED:     "Fix 09: misscount-comment")
# REMOVED: ok += r; fail += not r

# REMOVED: # Fix 16: DEX fee collectors match fix (bugs/21526) - prevents double-counting net fee as service fee
# REMOVED: # Already in upstream since March 18 (2fc53a212), needed for March 12 builds
# REMOVED: DEX_C = f"{REPO}/cellframe-sdk/modules/service/dex/dap_chain_net_srv_dex.c"
# REMOVED: r = apply_fix(DEX_C,
# REMOVED:     """            SUM_256_256(l_paid_net_fee, o->value, &l_paid_net_fee);
# REMOVED:             // Skip further processing if not also service fee
# REMOVED:             if (!is_srv_fee)
# REMOVED:                 continue;""",
# REMOVED:     """            SUM_256_256(l_paid_net_fee, o->value, &l_paid_net_fee);
# REMOVED:             continue;""",
# REMOVED:     "Fix 16: dex-fee-collectors-match (bugs/21526)")
# REMOVED: ok += r; fail += not r

print(f"\nInline patches: {ok} applied/skipped, {fail} failed")
sys.exit(1 if fail else 0)
