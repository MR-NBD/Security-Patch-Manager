#!/bin/bash
################################################################################
# UYUNI Errata Manager - QUICK START
#
# Esegui questo script sul SERVER UYUNI dopo aver copiato i file
################################################################################

echo "======================================================"
echo "  UYUNI ERRATA MANAGER - QUICK START"
echo "======================================================"
echo ""

# Check if we're root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Please run as root"
    exit 1
fi

# Check location
if [ ! -f /root/test-and-sync.sh ]; then
    echo "ERROR: /root/test-and-sync.sh not found"
    echo ""
    echo "Please copy files first:"
    echo "  scp test-and-sync.sh root@10.172.2.5:/root/"
    echo "  scp errata-sync-v2.5-IMPROVED.sh root@10.172.2.5:/root/errata-sync.sh"
    exit 1
fi

# Make scripts executable
echo "[1/5] Making scripts executable..."
chmod +x /root/test-and-sync.sh
chmod +x /root/errata-sync.sh 2>/dev/null || true
echo "✓ Done"
echo ""

# Test connectivity
echo "[2/5] Testing container connectivity..."
if /root/test-and-sync.sh test; then
    echo "✓ Containers are healthy"
else
    echo "✗ Container connectivity issues - check manually"
    echo "  Run: /root/test-and-sync.sh test"
    exit 1
fi
echo ""

# Show health
echo "[3/5] Checking system health..."
/root/test-and-sync.sh health
echo ""

# Ask for sync
echo "[4/5] Ready to perform FULL SYNC"
echo ""
echo "This will:"
echo "  - Sync Ubuntu USN (2-5 min)"
echo "  - Sync Debian DSA (15-30 min)"
echo "  - Sync OVAL definitions (10-20 min)"
echo "  - Update package cache (5-10 min)"
echo "  - Push errata to UYUNI (5-15 min)"
echo "  - Enrich CVE from NVD (optional)"
echo ""
echo "Total time: 30-45 minutes"
echo ""
read -p "Start full sync now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Starting full sync..."
    echo "Logs: /var/log/errata-sync.log"
    echo ""
    /root/test-and-sync.sh full

    echo ""
    echo "[5/5] Setup automation (cron)"
    read -p "Setup weekly cron job? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cat > /etc/cron.d/errata-sync << 'EOF'
# UYUNI Errata Manager - Automated Sync
# Full sync every Sunday at 02:00
0 2 * * 0 root /root/errata-sync.sh >> /var/log/errata-sync.log 2>&1

# Quick sync every Wednesday at 02:00
0 2 * * 3 root /root/test-and-sync.sh quick >> /var/log/errata-sync-quick.log 2>&1
EOF

        # Setup log rotation
        cat > /etc/logrotate.d/errata-sync << 'EOF'
/var/log/errata-sync.log {
    weekly
    rotate 12
    compress
    missingok
    notifempty
}

/var/log/errata-sync-quick.log {
    weekly
    rotate 12
    compress
    missingok
    notifempty
}
EOF

        echo "✓ Cron job installed: /etc/cron.d/errata-sync"
        echo "✓ Log rotation configured"
        cat /etc/cron.d/errata-sync
    fi
else
    echo ""
    echo "Skipped full sync. Run manually later with:"
    echo "  /root/test-and-sync.sh full"
fi

echo ""
echo "======================================================"
echo "  SETUP COMPLETE!"
echo "======================================================"
echo ""
echo "Next steps:"
echo "  1. Verify patches in UYUNI Web UI:"
echo "     Patches → Patch List → Filter: 'UYUNI Errata Manager'"
echo ""
echo "  2. Check CVE Audit:"
echo "     Audit → CVE Audit → Search for a CVE"
echo ""
echo "  3. Monitor sync logs:"
echo "     tail -f /var/log/errata-sync.log"
echo ""
echo "  4. Check statistics:"
echo "     /root/test-and-sync.sh stats"
echo ""
echo "Documentation: /root/GUIDA-OPERATIVA-FIX.md"
echo ""
