#!/bin/bash
# Reset cellframe-node.cfg on all 5 nodes to fresh defaults + unique ports + min_links
# Run from cc12 (ssh -p 222 root@84.86.175.121)

set -e
DEB="/root/cellframe-builds/cellframe-node-5.7-28-rwd-amd64-10patches-v2-dexfix.deb"
DATE=$(date +%Y%m%d-%H%M)

declare -A PORTS
PORTS[local]=8279
PORTS[root@192.168.2.5]=8179
PORTS[root@192.168.2.21]=7379
PORTS[root@192.168.2.24]=8111

# cc12 (local)
echo "=== cc12 (port 8279) ==="
cp /opt/cellframe-node/etc/cellframe-node.cfg /root/cellframe-builds/cellframe-node.cfg.cc12.bak-$DATE
rm /opt/cellframe-node/etc/cellframe-node.cfg
dpkg -i $DEB 2>&1 | tail -3
sed -i "s/listen_address=\[0.0.0.0:8079\]/listen_address=[0.0.0.0:8279]/" /opt/cellframe-node/etc/cellframe-node.cfg
sed -i "s/#ext_port_tcp=8089/ext_port_tcp=8279/" /opt/cellframe-node/etc/cellframe-node.cfg
sed -i '/ext_port_tcp=8279/a min_links_num=10' /opt/cellframe-node/etc/cellframe-node.cfg
sed -i 's/^auto_proc=false/auto_proc=true/' /opt/cellframe-node/etc/cellframe-node.cfg
grep -q 'auto_proc=true' /opt/cellframe-node/etc/cellframe-node.cfg || sed -i '/^\[mempool\]/a auto_proc=true' /opt/cellframe-node/etc/cellframe-node.cfg
sed -i 's/^enabled=false/enabled=true/' /opt/cellframe-node/etc/cellframe-node.cfg
echo "cc12 done"

# cc09, cc08, cc11
for info in "root@192.168.2.5 8179 cc09" "root@192.168.2.21 7379 cc08" "root@192.168.2.24 8111 cc11"; do
    host=$(echo "$info" | awk '{print $1}')
    port=$(echo "$info" | awk '{print $2}')
    name=$(echo "$info" | awk '{print $3}')
    echo "=== $name (port $port) ==="
    ssh $host "cp /opt/cellframe-node/etc/cellframe-node.cfg /root/cellframe-builds/cellframe-node.cfg.$name.bak-$DATE && \
        rm /opt/cellframe-node/etc/cellframe-node.cfg && \
        dpkg -i /tmp/$(basename $DEB) 2>&1 | tail -3 && \
        sed -i 's/listen_address=\[0.0.0.0:8079\]/listen_address=[0.0.0.0:$port]/' /opt/cellframe-node/etc/cellframe-node.cfg && \
        sed -i 's/#ext_port_tcp=8089/ext_port_tcp=$port/' /opt/cellframe-node/etc/cellframe-node.cfg && \
        sed -i '/ext_port_tcp=$port/a min_links_num=10' /opt/cellframe-node/etc/cellframe-node.cfg && \
        sed -i 's/^auto_proc=false/auto_proc=true/' /opt/cellframe-node/etc/cellframe-node.cfg
grep -q 'auto_proc=true' /opt/cellframe-node/etc/cellframe-node.cfg || sed -i '/^\[mempool\]/a auto_proc=true' /opt/cellframe-node/etc/cellframe-node.cfg
sed -i 's/^enabled=false/enabled=true/' /opt/cellframe-node/etc/cellframe-node.cfg"
    echo "$name done"
done

# cc20 (port 37)
echo "=== cc20 (port 8037) ==="
ssh -p 37 root@84.86.175.121 "cp /opt/cellframe-node/etc/cellframe-node.cfg /root/cellframe-builds/cellframe-node.cfg.cc20.bak-$DATE && \
    rm /opt/cellframe-node/etc/cellframe-node.cfg && \
    dpkg -i /tmp/$(basename $DEB) 2>&1 | tail -3 && \
    sed -i 's/listen_address=\[0.0.0.0:8079\]/listen_address=[0.0.0.0:8037]/' /opt/cellframe-node/etc/cellframe-node.cfg && \
    sed -i 's/#ext_port_tcp=8089/ext_port_tcp=8037/' /opt/cellframe-node/etc/cellframe-node.cfg && \
    sed -i '/ext_port_tcp=8037/a min_links_num=10' /opt/cellframe-node/etc/cellframe-node.cfg && \
    sed -i 's/^auto_proc=false/auto_proc=true/' /opt/cellframe-node/etc/cellframe-node.cfg
grep -q 'auto_proc=true' /opt/cellframe-node/etc/cellframe-node.cfg || sed -i '/^\[mempool\]/a auto_proc=true' /opt/cellframe-node/etc/cellframe-node.cfg
sed -i 's/^enabled=false/enabled=true/' /opt/cellframe-node/etc/cellframe-node.cfg"
echo "cc20 done"

echo ""
echo "=== All nodes reset. Backbone.cfg untouched. ==="
