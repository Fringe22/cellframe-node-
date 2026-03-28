#!/bin/bash
# Cellframe Node Monitor - checks all 5 validators
export LC_ALL=C

LOG="/root/cellframe-node/monitor.log"
DATE=$(date +%Y%m%d)

# 6f baselines (blocks/hr)
B_CC12=1.5; B_CC09=4.0; B_CC08=4.5; B_CC20=3.4; B_CC11=3.8
B_TOTAL=$(echo "$B_CC12 + $B_CC09 + $B_CC08 + $B_CC20 + $B_CC11" | bc)
# Per-node CELL reward/block (from actual chain data, varies by stake weight)
RW_CC12=1.383; RW_CC09=1.393; RW_CC08=1.393; RW_CC20=1.434; RW_CC11=1.381

# Get block counts for today
CC12=$(timeout 120 /opt/cellframe-node/bin/cellframe-node-cli block -net Backbone -chain main list signed -cert backbone.cc12 -from_date ${DATE:2} 2>/dev/null | grep -c "block number")
CC09=$(ssh root@192.168.2.5 "timeout 120 /opt/cellframe-node/bin/cellframe-node-cli block -net Backbone -chain main list signed -cert backbone.cc09 -from_date ${DATE:2} 2>/dev/null | grep -c \"block number\"" 2>/dev/null)
CC08=$(ssh root@192.168.2.21 "timeout 120 /opt/cellframe-node/bin/cellframe-node-cli block -net Backbone -chain main list signed -cert backbone.cc08 -from_date ${DATE:2} 2>/dev/null | grep -c \"block number\"" 2>/dev/null)
CC20=$(ssh -p 37 root@84.86.175.121 "timeout 120 /opt/cellframe-node/bin/cellframe-node-cli block -net Backbone -chain main list signed -cert backbone.cc20 -from_date ${DATE:2} 2>/dev/null | grep -c \"block number\"" 2>/dev/null)
CC11=$(ssh root@192.168.2.24 "timeout 120 /opt/cellframe-node/bin/cellframe-node-cli block -net Backbone -chain main list signed -cert backbone.cc11 -from_date ${DATE:2} 2>/dev/null | grep -c \"block number\"" 2>/dev/null)

# Hours elapsed today
HOUR=$(date +%H); MIN=$(date +%M)
H=$(echo "scale=2; $HOUR + $MIN / 60" | bc)
if [ "$(echo "$H < 0.5" | bc)" -eq 1 ]; then H="0.5"; fi

TOTAL=$((CC12 + CC09 + CC08 + CC20 + CC11))

# Calculate: rate, earned, projected, vs_6f
calc_row() {
    local blk=$1 base=$2 rw=$3
    local rate_raw=$(echo "scale=4; $blk / $H" | bc)
    RATE=$(printf "%.1f" "$rate_raw")
    EARNED=$(printf "%.2f" $(echo "scale=4; $blk * $rw" | bc))
    PROJ=$(printf "%.1f" $(echo "scale=4; $rate_raw * 24 * $rw" | bc))
    if [ "$(echo "$base > 0" | bc)" -eq 1 ]; then
        local diff=$(printf "%.0f" $(echo "scale=4; ($rate_raw / $base - 1) * 100" | bc))
        if [ "${diff:-0}" -ge 0 ] 2>/dev/null; then
            VS="+${diff}%"
        else
            VS="${diff}%"
        fi
    else
        VS="N/A"
    fi
}

calc_row $CC12 $B_CC12 $RW_CC12; R12_RATE=$RATE; R12_EARNED=$EARNED; R12_PROJ=$PROJ; R12_VS=$VS
calc_row $CC09 $B_CC09 $RW_CC09; R09_RATE=$RATE; R09_EARNED=$EARNED; R09_PROJ=$PROJ; R09_VS=$VS
calc_row $CC08 $B_CC08 $RW_CC08; R08_RATE=$RATE; R08_EARNED=$EARNED; R08_PROJ=$PROJ; R08_VS=$VS
calc_row $CC20 $B_CC20 $RW_CC20; R20_RATE=$RATE; R20_EARNED=$EARNED; R20_PROJ=$PROJ; R20_VS=$VS
calc_row $CC11 $B_CC11 $RW_CC11; R11_RATE=$RATE; R11_EARNED=$EARNED; R11_PROJ=$PROJ; R11_VS=$VS

# Total uses weighted average reward
TOTAL_EARNED=$(echo "scale=2; $CC12 * $RW_CC12 + $CC09 * $RW_CC09 + $CC08 * $RW_CC08 + $CC20 * $RW_CC20 + $CC11 * $RW_CC11" | bc)
if [ "$TOTAL" -gt 0 ] 2>/dev/null; then
    RW_AVG=$(echo "scale=4; $TOTAL_EARNED / $TOTAL" | bc)
else
    RW_AVG=1.39
fi
calc_row $TOTAL $B_TOTAL $RW_AVG; RT_RATE=$RATE; RT_EARNED=$EARNED; RT_PROJ=$PROJ; RT_VS=$VS

# Check status and errors
WARN=""
for info in "cc12 local" "cc09 root@192.168.2.5" "cc08 root@192.168.2.21" "cc11 root@192.168.2.24"; do
    name=$(echo "$info" | awk '{print $1}')
    host=$(echo "$info" | awk '{print $2}')
    if [ "$host" = "local" ]; then
        ST=$(timeout 120 /opt/cellframe-node/bin/cellframe-node-cli net -net Backbone get status 2>/dev/null | grep "NET_STATE" | tail -1 | awk '{print $2}')
        RB=$(tail -500 /opt/cellframe-node/var/log/cellframe-node.log | grep -c "No previous state registered")
    else
        ST=$(ssh "$host" "timeout 120 /opt/cellframe-node/bin/cellframe-node-cli net -net Backbone get status 2>/dev/null | grep NET_STATE | tail -1 | awk '{print \$2}'" 2>/dev/null)
        RB=$(ssh "$host" "tail -500 /opt/cellframe-node/var/log/cellframe-node.log | grep -c 'No previous state registered'" 2>/dev/null)
    fi
    [ -n "$ST" ] && [ "$ST" != "NET_STATE_ONLINE" ] && WARN="${WARN}  WARN: $name status=$ST\n"
    [ "${RB:-0}" -gt 0 ] 2>/dev/null && WARN="${WARN}  WARN: $name ${RB} rollback errors\n"
done
# cc20 separately
ST=$(ssh -p 37 root@84.86.175.121 "timeout 120 /opt/cellframe-node/bin/cellframe-node-cli net -net Backbone get status 2>/dev/null | grep NET_STATE | tail -1 | awk '{print \$2}'" 2>/dev/null)
RB=$(ssh -p 37 root@84.86.175.121 "tail -500 /opt/cellframe-node/var/log/cellframe-node.log | grep -c 'No previous state registered'" 2>/dev/null)
[ -n "$ST" ] && [ "$ST" != "NET_STATE_ONLINE" ] && WARN="${WARN}  WARN: cc20 status=$ST\n"
[ "${RB:-0}" -gt 0 ] 2>/dev/null && WARN="${WARN}  WARN: cc20 ${RB} rollback errors\n"

# Output table
{
echo "=== $(date) === (${H}h elapsed)"
echo "┌───────┬────────┬─────────┬─────────────┬──────────────────────┬───────┐"
echo "│ Node  │ Blocks │ Rate/hr │ CELL earned │ Projected daily CELL │ vs 6f │"
echo "├───────┼────────┼─────────┼─────────────┼──────────────────────┼───────┤"
printf "│ cc12  │ %-6s │ %-7s │ %-11s │ %-20s │ %-5s │\n" "$CC12" "$R12_RATE" "$R12_EARNED" "$R12_PROJ" "$R12_VS"
echo "├───────┼────────┼─────────┼─────────────┼──────────────────────┼───────┤"
printf "│ cc09  │ %-6s │ %-7s │ %-11s │ %-20s │ %-5s │\n" "$CC09" "$R09_RATE" "$R09_EARNED" "$R09_PROJ" "$R09_VS"
echo "├───────┼────────┼─────────┼─────────────┼──────────────────────┼───────┤"
printf "│ cc08  │ %-6s │ %-7s │ %-11s │ %-20s │ %-5s │\n" "$CC08" "$R08_RATE" "$R08_EARNED" "$R08_PROJ" "$R08_VS"
echo "├───────┼────────┼─────────┼─────────────┼──────────────────────┼───────┤"
printf "│ cc20  │ %-6s │ %-7s │ %-11s │ %-20s │ %-5s │\n" "$CC20" "$R20_RATE" "$R20_EARNED" "$R20_PROJ" "$R20_VS"
echo "├───────┼────────┼─────────┼─────────────┼──────────────────────┼───────┤"
printf "│ cc11  │ %-6s │ %-7s │ %-11s │ %-20s │ %-5s │\n" "$CC11" "$R11_RATE" "$R11_EARNED" "$R11_PROJ" "$R11_VS"
echo "├───────┼────────┼─────────┼─────────────┼──────────────────────┼───────┤"
printf "│ Total │ %-6s │ %-7s │ %-11s │ %-20s │ %-5s │\n" "$TOTAL" "$RT_RATE" "$RT_EARNED" "$RT_PROJ" "$RT_VS"
echo "└───────┴────────┴─────────┴─────────────┴──────────────────────┴───────┘"
if [ -n "$WARN" ]; then echo -e "$WARN"; else echo "All nodes ONLINE, no errors"; fi
echo ""
} >> "$LOG"
