#!/bin/bash
################################################################################
# Monitor OVAL Sync Progress
################################################################################

PUBLIC_API="http://4.232.3.251:5000"

echo "======================================================"
echo "  OVAL Sync Progress Monitor"
echo "======================================================"
echo ""

echo "Checking container logs (last 50 lines)..."
echo "------------------------------------------------------"
az container logs \
  --resource-group test_group \
  --name aci-errata-api 2>/dev/null | tail -50

echo ""
echo "======================================================"
echo "Current Statistics:"
echo "------------------------------------------------------"

if stats=$(curl -s -m 10 "$PUBLIC_API/api/stats/overview" 2>&1); then
    echo "$stats" | python3 -m json.tool 2>/dev/null || echo "$stats"
else
    echo "ERROR: Cannot reach API"
fi

echo ""
echo "======================================================"
echo "To monitor in real-time, run in another window:"
echo "  az container logs --resource-group test_group --name aci-errata-api --follow"
echo ""
echo "Or check every 10 seconds:"
echo "  watch -n 10 'curl -s $PUBLIC_API/api/stats/overview | python3 -m json.tool'"
echo "======================================================"
