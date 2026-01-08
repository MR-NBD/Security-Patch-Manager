#!/bin/bash
################################################################################
# Check Container IPs and Status
# Questo script verifica lo stato dei container e aggiorna gli script con gli IP corretti
################################################################################

echo "======================================================"
echo "  UYUNI ERRATA MANAGER - Container Status Check"
echo "======================================================"
echo ""

# Check if Azure CLI is available
if ! command -v az &> /dev/null; then
    echo "ERROR: Azure CLI not found. Please install it first."
    exit 1
fi

echo "[1/3] Checking container status in Azure..."
echo ""

# Get internal container status
echo "Internal Container:"
INTERNAL_STATUS=$(az container show \
    --resource-group ASL0603-spoke10-rg-spoke-italynorth \
    --name aci-errata-api-internal \
    --query "{State:instanceView.state, IP:ipAddress.ip, Image:containers[0].image}" \
    --output json 2>&1)

if [ $? -eq 0 ]; then
    echo "$INTERNAL_STATUS" | python3 -m json.tool
    INTERNAL_IP=$(echo "$INTERNAL_STATUS" | grep -o '"IP": "[^"]*"' | cut -d'"' -f4)
    INTERNAL_STATE=$(echo "$INTERNAL_STATUS" | grep -o '"State": "[^"]*"' | cut -d'"' -f4)
else
    echo "ERROR: Failed to get internal container status"
    echo "$INTERNAL_STATUS"
    exit 1
fi

echo ""

# Get public container status
echo "Public Container:"
PUBLIC_STATUS=$(az container show \
    --resource-group test_group \
    --name aci-errata-api \
    --query "{State:instanceView.state, IP:ipAddress.ip, Image:containers[0].image}" \
    --output json 2>&1)

if [ $? -eq 0 ]; then
    echo "$PUBLIC_STATUS" | python3 -m json.tool
    PUBLIC_IP=$(echo "$PUBLIC_STATUS" | grep -o '"IP": "[^"]*"' | cut -d'"' -f4)
    PUBLIC_STATE=$(echo "$PUBLIC_STATUS" | grep -o '"State": "[^"]*"' | cut -d'"' -f4)
else
    echo "ERROR: Failed to get public container status"
    echo "$PUBLIC_STATUS"
    exit 1
fi

echo ""
echo "======================================================"

# Check if containers are running
if [ "$INTERNAL_STATE" != "Running" ]; then
    echo "WARNING: Internal container is $INTERNAL_STATE"
    read -p "Start internal container? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Starting internal container..."
        az container start --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal
        sleep 10
        # Get new status
        INTERNAL_STATUS=$(az container show --resource-group ASL0603-spoke10-rg-spoke-italynorth --name aci-errata-api-internal --query "{State:instanceView.state, IP:ipAddress.ip}" --output json)
        INTERNAL_IP=$(echo "$INTERNAL_STATUS" | grep -o '"IP": "[^"]*"' | cut -d'"' -f4)
        INTERNAL_STATE=$(echo "$INTERNAL_STATUS" | grep -o '"State": "[^"]*"' | cut -d'"' -f4)
        echo "New state: $INTERNAL_STATE, IP: $INTERNAL_IP"
    fi
fi

if [ "$PUBLIC_STATE" != "Running" ]; then
    echo "WARNING: Public container is $PUBLIC_STATE"
    read -p "Start public container? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Starting public container..."
        az container start --resource-group test_group --name aci-errata-api
        sleep 10
        # Get new status
        PUBLIC_STATUS=$(az container show --resource-group test_group --name aci-errata-api --query "{State:instanceView.state, IP:ipAddress.ip}" --output json)
        PUBLIC_IP=$(echo "$PUBLIC_STATUS" | grep -o '"IP": "[^"]*"' | cut -d'"' -f4)
        PUBLIC_STATE=$(echo "$PUBLIC_STATUS" | grep -o '"State": "[^"]*"' | cut -d'"' -f4)
        echo "New state: $PUBLIC_STATE, IP: $PUBLIC_IP"
    fi
fi

echo ""
echo "[2/3] Current IPs:"
echo "  Public Container:   $PUBLIC_IP"
echo "  Internal Container: $INTERNAL_IP"
echo ""

# Check if IPs in scripts need updating
echo "[3/3] Checking script configuration..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/test-and-sync.sh" ]; then
    CURRENT_INTERNAL=$(grep "INTERNAL_API=" "$SCRIPT_DIR/test-and-sync.sh" | head -1 | grep -o 'http://[^:]*' | cut -d'/' -f3)
    CURRENT_PUBLIC=$(grep "PUBLIC_API=" "$SCRIPT_DIR/test-and-sync.sh" | head -1 | grep -o 'http://[^:]*' | cut -d'/' -f3)

    echo "Script IPs:"
    echo "  Public:   $CURRENT_PUBLIC"
    echo "  Internal: $CURRENT_INTERNAL"
    echo ""

    if [ "$CURRENT_INTERNAL" != "$INTERNAL_IP" ] || [ "$CURRENT_PUBLIC" != "$PUBLIC_IP" ]; then
        echo "WARNING: Script IPs don't match current container IPs!"
        echo ""
        echo "Expected:"
        echo "  PUBLIC_API=\"http://$PUBLIC_IP:5000\""
        echo "  INTERNAL_API=\"http://$INTERNAL_IP:5000\""
        echo ""
        read -p "Update scripts automatically? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            # Update test-and-sync.sh
            if [ -f "$SCRIPT_DIR/test-and-sync.sh" ]; then
                sed -i "s|PUBLIC_API=\"http://[^:]*:5000\"|PUBLIC_API=\"http://$PUBLIC_IP:5000\"|g" "$SCRIPT_DIR/test-and-sync.sh"
                sed -i "s|INTERNAL_API=\"http://[^:]*:5000\"|INTERNAL_API=\"http://$INTERNAL_IP:5000\"|g" "$SCRIPT_DIR/test-and-sync.sh"
                echo "✓ Updated test-and-sync.sh"
            fi

            # Update errata-sync-v2.5-IMPROVED.sh
            if [ -f "$SCRIPT_DIR/errata-sync-v2.5-IMPROVED.sh" ]; then
                sed -i "s|PUBLIC_API=\"\${PUBLIC_API:-http://[^:]*:5000}\"|PUBLIC_API=\"\${PUBLIC_API:-http://$PUBLIC_IP:5000}\"|g" "$SCRIPT_DIR/errata-sync-v2.5-IMPROVED.sh"
                sed -i "s|INTERNAL_API=\"\${INTERNAL_API:-http://[^:]*:5000}\"|INTERNAL_API=\"\${INTERNAL_API:-http://$INTERNAL_IP:5000}\"|g" "$SCRIPT_DIR/errata-sync-v2.5-IMPROVED.sh"
                echo "✓ Updated errata-sync-v2.5-IMPROVED.sh"
            fi

            echo ""
            echo "Scripts updated successfully!"
        else
            echo ""
            echo "Manual update required. Edit the following files:"
            echo "  - test-and-sync.sh"
            echo "  - errata-sync-v2.5-IMPROVED.sh"
            echo ""
            echo "Change IPs to:"
            echo "  PUBLIC_API=\"http://$PUBLIC_IP:5000\""
            echo "  INTERNAL_API=\"http://$INTERNAL_IP:5000\""
        fi
    else
        echo "✓ Script IPs are correct!"
    fi
fi

echo ""
echo "======================================================"
echo "Summary:"
echo "  Public Container:  $PUBLIC_STATE @ $PUBLIC_IP"
echo "  Internal Container: $INTERNAL_STATE @ $INTERNAL_IP"
echo ""

if [ "$PUBLIC_STATE" = "Running" ] && [ "$INTERNAL_STATE" = "Running" ]; then
    echo "✓ Both containers are Running"
    echo ""
    echo "Next steps:"
    echo "  1. Copy updated scripts to UYUNI server:"
    echo "     scp test-and-sync.sh root@10.172.2.5:/root/"
    echo "     scp errata-sync-v2.5-IMPROVED.sh root@10.172.2.5:/root/errata-sync.sh"
    echo ""
    echo "  2. Test connectivity from UYUNI server:"
    echo "     ssh root@10.172.2.5"
    echo "     /root/test-and-sync.sh test"
    echo ""
    echo "  3. Run full sync:"
    echo "     /root/test-and-sync.sh full"
else
    echo "✗ One or more containers are not Running"
    echo "  Please start them and run this script again"
fi

echo "======================================================"
