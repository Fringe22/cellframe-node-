#!/usr/bin/env python3
"""Inline patches for cellframe-node that cannot be expressed as git diff patches.
These modify the source directly after git patches are applied."""

import sys

REPO = "/root/cellframe-node"
ESBOCS_C = f"{REPO}/cellframe-sdk/modules/consensus/esbocs/dap_chain_cs_esbocs.c"
NET_C = f"{REPO}/cellframe-sdk/modules/net/dap_chain_net.c"

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

# Fix 10: Rollback log level
r = apply_fix(ESBOCS_C,
    'L_ERROR, "No previous state registered',
    'L_DEBUG, "No previous state registered',
    "Fix 10: rollback-log-level")
ok += r; fail += not r

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

# Fix 08: Penalty kick threshold = 10 (check header file, not .c)
ESBOCS_H = f"{REPO}/cellframe-sdk/modules/consensus/esbocs/include/dap_chain_cs_esbocs.h"
r = apply_fix(ESBOCS_H,
    "#define DAP_CHAIN_ESBOCS_PENALTY_KICK   3U",
    "#define DAP_CHAIN_ESBOCS_PENALTY_KICK   10U      // syncfix3-fix8: raised from 3 to reduce false kicks",
    "Fix 08: penalty-kick-10")
ok += r; fail += not r

print(f"\nInline patches: {ok} applied/skipped, {fail} failed")
sys.exit(1 if fail else 0)
