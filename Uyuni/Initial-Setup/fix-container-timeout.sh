#!/bin/bash
################################################################################
# Fix Container Timeout - Rebuild con timeout aumentato
#
# Questo script:
# 1. Fa rebuild dell'immagine con timeout 1800s (30min)
# 2. Rideploya il container pubblico
################################################################################

set -euo pipefail

ACR_NAME="acaborerrata"
IMAGE_TAG="v2.5-timeout-fix"
RG_PUBLIC="test_group"
CONTAINER_PUBLIC="aci-errata-api"

echo "======================================================"
echo "  Fix Container Timeout"
echo "======================================================"
echo ""

# Check files
if [ ! -f "app-v2.5-IMPROVED.py" ]; then
    echo "ERROR: app-v2.5-IMPROVED.py not found"
    echo "Run this script from the Initial-Setup directory"
    exit 1
fi

if [ ! -f "Dockerfile.api-timeout-fix" ]; then
    echo "ERROR: Dockerfile.api-timeout-fix not found"
    exit 1
fi

echo "Step 1: Building new image with timeout=1800s..."
echo "------------------------------------------------------"

az acr build \
  --registry "$ACR_NAME" \
  --image "errata-api:$IMAGE_TAG" \
  --file Dockerfile.api-timeout-fix .

if [ $? -ne 0 ]; then
    echo "ERROR: Build failed"
    exit 1
fi

echo ""
echo "✓ Build completed successfully"
echo ""

# Get current container config
echo "Step 2: Getting current container configuration..."
echo "------------------------------------------------------"

CURRENT_CONFIG=$(az container show \
  --resource-group "$RG_PUBLIC" \
  --name "$CONTAINER_PUBLIC" \
  --query "{cpu:containers[0].resources.requests.cpu, memory:containers[0].resources.requests.memoryInGB, env:containers[0].environmentVariables}" \
  --output json)

echo "$CURRENT_CONFIG"
echo ""

# Get ACR password
echo "Step 3: Getting ACR credentials..."
echo "------------------------------------------------------"

ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)

if [ -z "$ACR_PASSWORD" ]; then
    echo "ERROR: Could not get ACR password"
    exit 1
fi

echo "✓ Got ACR credentials"
echo ""

# Delete old container
echo "Step 4: Deleting old container..."
echo "------------------------------------------------------"

read -p "This will delete the current public container. Continue? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted"
    exit 0
fi

az container delete \
  --resource-group "$RG_PUBLIC" \
  --name "$CONTAINER_PUBLIC" \
  --yes

echo "✓ Old container deleted"
echo ""

# Deploy new container
echo "Step 5: Deploying new container with timeout fix..."
echo "------------------------------------------------------"

az container create \
  --resource-group "$RG_PUBLIC" \
  --name "$CONTAINER_PUBLIC" \
  --image "$ACR_NAME.azurecr.io/errata-api:$IMAGE_TAG" \
  --registry-login-server "$ACR_NAME.azurecr.io" \
  --registry-username "$ACR_NAME" \
  --registry-password "$ACR_PASSWORD" \
  --os-type Linux \
  --cpu 1 \
  --memory 1.5 \
  --ports 5000 \
  --ip-address Public \
  --restart-policy Always \
  --environment-variables \
    FLASK_ENV=production \
    DATABASE_URL="postgresql://errataadmin:ErrataSecure2024@pg-errata-test.postgres.database.azure.com:5432/uyuni_errata?sslmode=require"

if [ $? -ne 0 ]; then
    echo "ERROR: Container deployment failed"
    exit 1
fi

echo ""
echo "✓ New container deployed"
echo ""

# Wait for container to start
echo "Step 6: Waiting for container to start..."
echo "------------------------------------------------------"

sleep 15

# Get new IP
NEW_IP=$(az container show \
  --resource-group "$RG_PUBLIC" \
  --name "$CONTAINER_PUBLIC" \
  --query "ipAddress.ip" \
  --output tsv)

echo "Container IP: $NEW_IP"
echo ""

# Test
echo "Step 7: Testing new container..."
echo "------------------------------------------------------"

if curl -s -m 10 "http://$NEW_IP:5000/api/health" | grep -q "ok"; then
    echo "✓ Container is healthy"
else
    echo "WARNING: Container health check failed"
    echo "Check logs with: az container logs --resource-group $RG_PUBLIC --name $CONTAINER_PUBLIC"
fi

echo ""
echo "======================================================"
echo "  FIX COMPLETED!"
echo "======================================================"
echo ""
echo "New container:"
echo "  - Image: errata-api:$IMAGE_TAG"
echo "  - Timeout: 1800s (30 minutes)"
echo "  - IP: $NEW_IP"
echo ""
echo "Update scripts with new IP if changed:"
echo "  sed -i 's|4.232.4.154|$NEW_IP|g' remote-sync.sh"
echo ""
echo "Test OVAL sync:"
echo "  curl -m 1800 -X POST http://$NEW_IP:5000/api/sync/oval?platform=all"
echo ""
