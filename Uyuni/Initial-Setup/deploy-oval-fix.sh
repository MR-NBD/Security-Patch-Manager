#!/bin/bash
################################################################################
# DEPLOY OVAL FIX - Rebuild Container con Timeout Aumentato
#
# Questo script:
# 1. Build nuova immagine con timeout 30 minuti (invece di 15)
# 2. Redeploy container pubblico
# 3. Test sync OVAL completo
#
# Usage:
#   ./deploy-oval-fix.sh [DATABASE_URL]
#
# Example:
#   ./deploy-oval-fix.sh "postgresql://user:pass@host:5432/dbname"
################################################################################

set -euo pipefail

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Configurazione
ACR_NAME="acaborerrata"
IMAGE_NAME="errata-api"
NEW_TAG="v2.5-oval-fixed"
RG_PUBLIC="test_group"
CONTAINER_PUBLIC="aci-errata-api"

# Database URL da parametro o da chiedere
DB_URL_INPUT="${1:-}"

echo "======================================================"
echo "  OVAL FIX DEPLOYMENT"
echo "======================================================"
echo ""
log_info "This script will:"
log_info "  1. Build new image with 30-min timeout"
log_info "  2. Redeploy public container"
log_info "  3. Test OVAL sync (all platforms)"
echo ""
log_warn "Estimated time: 20-30 minutes total"
echo ""

# Se DATABASE_URL fornito come parametro, mostralo
if [ -n "$DB_URL_INPUT" ]; then
    log_success "Database URL provided as parameter"
    log_info "URL: ${DB_URL_INPUT:0:50}..."
    echo ""
else
    log_info "Database URL will be:"
    log_info "  1. Retrieved from existing container, OR"
    log_info "  2. Requested interactively if not found"
    echo ""
fi

log_info "Usage examples:"
log_info "  ./deploy-oval-fix.sh"
log_info "  ./deploy-oval-fix.sh \"postgresql://user:pass@host:5432/db\""
echo ""

read -p "Continue? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Aborted by user"
    exit 0
fi

# ============================================================
# STEP 1: BUILD NEW IMAGE
# ============================================================
log_info "============================================================"
log_info "STEP 1: BUILDING NEW IMAGE WITH TIMEOUT FIX"
log_info "============================================================"
echo ""

log_info "Checking files..."
if [ ! -f "Dockerfile.api-timeout-fix" ]; then
    log_error "Dockerfile.api-timeout-fix not found!"
    exit 1
fi

if [ ! -f "app-v2.5-IMPROVED.py" ]; then
    log_error "app-v2.5-IMPROVED.py not found!"
    exit 1
fi

log_success "Files found"
echo ""

log_info "Starting Azure Container Registry build..."
log_info "Image: $ACR_NAME.azurecr.io/$IMAGE_NAME:$NEW_TAG"
log_warn "This will take 10-15 minutes..."
echo ""

if az acr build \
    --registry "$ACR_NAME" \
    --image "$IMAGE_NAME:$NEW_TAG" \
    --file Dockerfile.api-timeout-fix \
    .; then
    log_success "Image built successfully!"
else
    log_error "Build failed!"
    exit 1
fi

echo ""
log_info "Verifying image..."
if az acr repository show-tags \
    --name "$ACR_NAME" \
    --repository "$IMAGE_NAME" \
    --output table | grep -q "$NEW_TAG"; then
    log_success "Image verified in ACR"
else
    log_error "Image not found in ACR!"
    exit 1
fi

# ============================================================
# STEP 2: BACKUP CURRENT CONTAINER CONFIG
# ============================================================
log_info ""
log_info "============================================================"
log_info "STEP 2: BACKUP CURRENT CONTAINER"
log_info "============================================================"
echo ""

BACKUP_FILE="aci-errata-api-backup-$(date +%Y%m%d-%H%M%S).yaml"
log_info "Creating backup: $BACKUP_FILE"

if az container export \
    --resource-group "$RG_PUBLIC" \
    --name "$CONTAINER_PUBLIC" \
    --file "$BACKUP_FILE" 2>/dev/null; then
    log_success "Backup created: $BACKUP_FILE"
else
    log_warn "Could not create backup (container might not exist or already stopped)"
fi

# ============================================================
# STEP 3: GET DATABASE URL
# ============================================================
log_info ""
log_info "============================================================"
log_info "STEP 3: GET DATABASE URL"
log_info "============================================================"
echo ""

DB_URL=""

# 1. Usa DATABASE_URL fornito come parametro
if [ -n "$DB_URL_INPUT" ]; then
    DB_URL="$DB_URL_INPUT"
    log_success "Using DATABASE_URL from command line parameter"
    log_info "URL: ${DB_URL:0:50}..."
else
    # 2. Tenta di recuperarlo dal container esistente
    log_info "Attempting to retrieve DATABASE_URL from existing container..."
    DB_URL=$(az container show \
        --resource-group "$RG_PUBLIC" \
        --name "$CONTAINER_PUBLIC" \
        --query "containers[0].environmentVariables[?name=='DATABASE_URL'].value | [0]" \
        -o tsv 2>/dev/null || echo "")

    if [ -n "$DB_URL" ]; then
        log_success "Retrieved DATABASE_URL from existing container"
        log_info "URL: ${DB_URL:0:50}..."
    else
        # 3. Chiedi manualmente all'utente
        log_warn "Could not retrieve DATABASE_URL from existing container"
        log_info ""
        log_info "Please provide DATABASE_URL manually."
        log_info "Format: postgresql://user:password@host:port/database?sslmode=require"
        log_info ""
        log_info "Example:"
        log_info "  postgresql://errataadmin:ErrataSecure2024@pg-errata-test.postgres.database.azure.com:5432/uyuni_errata?sslmode=require"
        echo ""
        read -p "DATABASE_URL: " DB_URL

        if [ -z "$DB_URL" ]; then
            log_error "DATABASE_URL is required!"
            exit 1
        fi

        log_success "DATABASE_URL provided manually"
    fi
fi

# Valida formato base (deve contenere postgresql://)
if [[ ! "$DB_URL" =~ ^postgresql:// ]]; then
    log_error "Invalid DATABASE_URL format! Must start with 'postgresql://'"
    exit 1
fi

log_success "Database URL validated: ${DB_URL:0:50}..."

# ============================================================
# STEP 4: DELETE OLD CONTAINER
# ============================================================
log_info ""
log_info "============================================================"
log_info "STEP 4: DELETE OLD CONTAINER"
log_info "============================================================"
echo ""

log_warn "Deleting old container..."
if az container delete \
    --resource-group "$RG_PUBLIC" \
    --name "$CONTAINER_PUBLIC" \
    --yes 2>/dev/null; then
    log_success "Old container deleted"
else
    log_warn "Container might not exist (ok if first deployment)"
fi

# Wait for deletion
log_info "Waiting for deletion to complete..."
sleep 10

# ============================================================
# STEP 5: DEPLOY NEW CONTAINER
# ============================================================
log_info ""
log_info "============================================================"
log_info "STEP 5: DEPLOY NEW CONTAINER"
log_info "============================================================"
echo ""

log_info "Deploying container with new image..."
log_info "Image: $ACR_NAME.azurecr.io/$IMAGE_NAME:$NEW_TAG"
echo ""

# Get ACR credentials
ACR_PASSWORD=$(az acr credential show --name "$ACR_NAME" --query "passwords[0].value" -o tsv)

if az container create \
    --resource-group "$RG_PUBLIC" \
    --name "$CONTAINER_PUBLIC" \
    --image "$ACR_NAME.azurecr.io/$IMAGE_NAME:$NEW_TAG" \
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
        DATABASE_URL="$DB_URL"; then
    log_success "Container deployed successfully!"
else
    log_error "Deployment failed!"
    exit 1
fi

# ============================================================
# STEP 6: WAIT FOR CONTAINER TO START
# ============================================================
log_info ""
log_info "Waiting for container to start..."
sleep 20

# Get new IP
NEW_IP=$(az container show \
    --resource-group "$RG_PUBLIC" \
    --name "$CONTAINER_PUBLIC" \
    --query "ipAddress.ip" \
    -o tsv)

log_success "Container started with IP: $NEW_IP"

# ============================================================
# STEP 7: TEST HEALTH
# ============================================================
log_info ""
log_info "============================================================"
log_info "STEP 7: TESTING CONTAINER HEALTH"
log_info "============================================================"
echo ""

log_info "Waiting for application to be ready..."
sleep 10

MAX_ATTEMPTS=12
attempt=1
while [ $attempt -le $MAX_ATTEMPTS ]; do
    log_info "Health check attempt $attempt/$MAX_ATTEMPTS..."

    if response=$(curl -s -m 10 "http://$NEW_IP:5000/api/health" 2>&1); then
        if echo "$response" | grep -q '"api".*"ok"'; then
            log_success "Container is healthy!"
            echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
            break
        fi
    fi

    if [ $attempt -eq $MAX_ATTEMPTS ]; then
        log_error "Health check failed after $MAX_ATTEMPTS attempts"
        log_info "Check logs with:"
        log_info "  az container logs --resource-group $RG_PUBLIC --name $CONTAINER_PUBLIC"
        exit 1
    fi

    sleep 10
    ((attempt++))
done

# ============================================================
# STEP 8: TEST OVAL SYNC
# ============================================================
log_info ""
log_info "============================================================"
log_info "STEP 8: TEST OVAL SYNC (CRITICAL)"
log_info "============================================================"
echo ""

log_warn "Starting OVAL sync test..."
log_warn "This will sync ALL platforms (ubuntu-noble, jammy, focal, debian)"
log_warn "Expected time: 30-50 minutes"
echo ""
read -p "Start OVAL sync now? (y/n): " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    log_info "Starting OVAL sync for platform=all..."
    log_info "Monitor in another terminal with:"
    log_info "  az container logs --resource-group $RG_PUBLIC --name $CONTAINER_PUBLIC --follow"
    echo ""

    # Start sync (non-blocking, with extended timeout)
    log_info "Calling API endpoint (timeout: 3600 seconds)..."

    if curl -s -m 3600 -X POST "http://$NEW_IP:5000/api/sync/oval?platform=all" > /tmp/oval-sync-result.json; then
        log_success "OVAL sync completed!"
        echo ""
        log_info "Results:"
        cat /tmp/oval-sync-result.json | python3 -m json.tool 2>/dev/null || cat /tmp/oval-sync-result.json
    else
        log_error "OVAL sync failed or timed out!"
        log_info "Check logs with:"
        log_info "  az container logs --resource-group $RG_PUBLIC --name $CONTAINER_PUBLIC"
        exit 1
    fi
else
    log_info "Skipping OVAL sync test"
    log_info "You can run it manually later with:"
    log_info "  curl -X POST http://$NEW_IP:5000/api/sync/oval?platform=all"
fi

# ============================================================
# SUMMARY
# ============================================================
log_info ""
log_info "============================================================"
log_info "DEPLOYMENT COMPLETE!"
log_info "============================================================"
echo ""
log_success "Container: $CONTAINER_PUBLIC"
log_success "Image: $ACR_NAME.azurecr.io/$IMAGE_NAME:$NEW_TAG"
log_success "IP: $NEW_IP"
log_success "Timeout: 1800 seconds (30 minutes)"
log_success "Database: ${DB_URL:0:50}..."
echo ""
log_info "If IP changed, update your scripts:"
log_info "  sed -i 's|PUBLIC_API=.*|PUBLIC_API=\"http://$NEW_IP:5000\"|g' remote-sync.sh"
log_info "  sed -i 's|PUBLIC_API=.*|PUBLIC_API=\"http://$NEW_IP:5000\"|g' errata-sync-v2.5-IMPROVED.sh"
echo ""
log_info "Next steps:"
log_info "  1. Test sync: ./remote-sync.sh full"
log_info "  2. Push to UYUNI: ssh root@10.172.2.5 '/root/uyuni-server-sync.sh quick'"
log_info "  3. Verify CVE in UYUNI Web UI: Audit → CVE Audit"
echo ""
log_info "For future deployments with custom DATABASE_URL:"
log_info "  ./deploy-oval-fix.sh \"postgresql://user:pass@host:5432/dbname\""
echo ""
