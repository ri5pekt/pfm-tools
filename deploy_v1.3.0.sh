#!/bin/bash

# Production Deployment Script for v1.3.0
# Run this on your production server: bash deploy_v1.3.0.sh

set -e  # Exit on error

echo "=========================================="
echo "PFM Tools v1.3.0 Production Deployment"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if we're in the right directory
if [ ! -f "docker-compose.prod.yml" ] && [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}✗${NC} Not in project directory"
    exit 1
fi

# Step 1: Pre-deployment checks
echo "Step 1: Running pre-deployment checks..."
if [ -f "pre-deployment-check.sh" ]; then
    bash pre-deployment-check.sh
    read -p "Continue with deployment? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Deployment cancelled"
        exit 0
    fi
else
    echo -e "${YELLOW}⚠${NC} pre-deployment-check.sh not found, skipping checks"
fi
echo ""

# Step 2: Backup
echo "Step 2: Creating backup..."
BACKUP_FILE="backup_$(date +%Y%m%d_%H%M%S).sql"
if docker-compose ps db 2>/dev/null | grep -q "Up" || docker compose ps db 2>/dev/null | grep -q "Up"; then
    DB_CONTAINER=$(docker-compose ps -q db 2>/dev/null || docker compose ps -q db 2>/dev/null)
    docker exec $DB_CONTAINER pg_dump -U pfmtools pfmtools > "$BACKUP_FILE" 2>/dev/null || {
        echo -e "${YELLOW}⚠${NC} Could not create database backup (may not be critical)"
    }
    echo -e "${GREEN}✓${NC} Backup created: $BACKUP_FILE"
else
    echo -e "${YELLOW}⚠${NC} Database container not running, skipping backup"
fi

# Tag current version
git tag v1.2.0-backup-$(date +%Y%m%d) 2>/dev/null || echo -e "${YELLOW}⚠${NC} Could not create git tag"
echo ""

# Step 3: Verify WooCommerce plugin update
echo "Step 3: WooCommerce Plugin Update Check"
echo -e "${YELLOW}⚠${NC} CRITICAL: Have you updated the WooCommerce plugin in WordPress?"
echo "   Required: Change METORIK_TZ from 'America/New_York' to 'UTC'"
read -p "Plugin updated? (yes/no): " plugin_updated
if [ "$plugin_updated" != "yes" ]; then
    echo -e "${RED}✗${NC} Please update the plugin FIRST, then run this script again"
    exit 1
fi
echo -e "${GREEN}✓${NC} Plugin update confirmed"
echo ""

# Step 4: Pull latest code
echo "Step 4: Pulling latest code..."
git fetch origin
CURRENT_COMMIT=$(git rev-parse HEAD)
REMOTE_COMMIT=$(git rev-parse origin/main)

if [ "$CURRENT_COMMIT" = "$REMOTE_COMMIT" ]; then
    echo -e "${GREEN}✓${NC} Already on latest commit"
else
    echo "Current: $CURRENT_COMMIT"
    echo "Remote:  $REMOTE_COMMIT"
    git pull origin main
    echo -e "${GREEN}✓${NC} Code updated"
fi

# Verify we're on the right commit
EXPECTED_COMMIT="48c92d8"
CURRENT_SHORT=$(git rev-parse --short HEAD)
if [ "$CURRENT_SHORT" = "$EXPECTED_COMMIT" ] || git log --oneline | head -1 | grep -q "v1.3.0"; then
    echo -e "${GREEN}✓${NC} On correct version (commit: $CURRENT_SHORT)"
else
    echo -e "${YELLOW}⚠${NC} Current commit: $CURRENT_SHORT (expected: $EXPECTED_COMMIT or v1.3.0)"
    read -p "Continue anyway? (yes/no): " continue_anyway
    if [ "$continue_anyway" != "yes" ]; then
        exit 1
    fi
fi
echo ""

# Step 5: Check for active jobs
echo "Step 5: Checking for active jobs..."
if docker-compose ps redis 2>/dev/null | grep -q "Up" || docker compose ps redis 2>/dev/null | grep -q "Up"; then
    REDIS_CONTAINER=$(docker-compose ps -q redis 2>/dev/null || docker compose ps -q redis 2>/dev/null)
    QUEUE_SIZE=$(docker exec $REDIS_CONTAINER redis-cli LLEN rq:queue:pfmtools 2>/dev/null || echo "0")
    if [ "$QUEUE_SIZE" -gt 0 ]; then
        echo -e "${YELLOW}⚠${NC} There are $QUEUE_SIZE jobs in the queue"
        read -p "Wait for jobs to complete? (yes/no): " wait_jobs
        if [ "$wait_jobs" = "yes" ]; then
            echo "Waiting for queue to empty..."
            while [ "$QUEUE_SIZE" -gt 0 ]; do
                sleep 5
                QUEUE_SIZE=$(docker exec $REDIS_CONTAINER redis-cli LLEN rq:queue:pfmtools 2>/dev/null || echo "0")
                echo "  Queue size: $QUEUE_SIZE"
            done
            echo -e "${GREEN}✓${NC} Queue is empty"
        fi
    else
        echo -e "${GREEN}✓${NC} No active jobs in queue"
    fi
fi
echo ""

# Step 6: Build new images
echo "Step 6: Building Docker images..."
if [ -f "docker-compose.prod.yml" ]; then
    docker-compose -f docker-compose.prod.yml build
else
    docker-compose build
fi
echo -e "${GREEN}✓${NC} Images built"
echo ""

# Step 7: Restart services
echo "Step 7: Restarting services..."
echo "Choose restart strategy:"
echo "1. Rolling restart (zero downtime, recommended)"
echo "2. Full restart (faster, brief downtime)"
read -p "Choice (1 or 2): " restart_choice

if [ "$restart_choice" = "1" ]; then
    echo "Performing rolling restart..."

    # Restart workers one at a time
    if [ -f "docker-compose.prod.yml" ]; then
        docker-compose -f docker-compose.prod.yml restart worker
        sleep 10
        docker-compose -f docker-compose.prod.yml restart worker2 2>/dev/null || echo "worker2 not found, skipping"
        sleep 10
        docker-compose -f docker-compose.prod.yml restart backend
        sleep 10
        docker-compose -f docker-compose.prod.yml restart scheduler
    else
        docker-compose restart worker
        sleep 10
        docker-compose restart worker2 2>/dev/null || echo "worker2 not found, skipping"
        sleep 10
        docker-compose restart backend
        sleep 10
        docker-compose restart scheduler
    fi
else
    echo "Performing full restart..."
    if [ -f "docker-compose.prod.yml" ]; then
        docker-compose -f docker-compose.prod.yml down
        docker-compose -f docker-compose.prod.yml up -d --scale worker=2
    else
        docker-compose down
        docker-compose up -d
    fi
fi
echo -e "${GREEN}✓${NC} Services restarted"
echo ""

# Step 8: Wait for services to be ready
echo "Step 8: Waiting for services to be ready..."
sleep 30
echo -e "${GREEN}✓${NC} Services should be ready"
echo ""

# Step 9: Verify deployment
echo "Step 9: Verifying deployment..."
echo ""

# Check service status
echo "Service status:"
if [ -f "docker-compose.prod.yml" ]; then
    docker-compose -f docker-compose.prod.yml ps
else
    docker-compose ps
fi
echo ""

# Verify scheduled jobs
echo "Verifying scheduled jobs..."
if [ -f "verify_scheduled_jobs.py" ]; then
    if [ -f "docker-compose.prod.yml" ]; then
        docker-compose -f docker-compose.prod.yml exec backend python verify_scheduled_jobs.py || \
        docker-compose -f docker-compose.prod.yml exec -T backend python /app/verify_scheduled_jobs.py
    else
        docker-compose exec backend python verify_scheduled_jobs.py || \
        docker-compose exec -T backend python /app/verify_scheduled_jobs.py
    fi
else
    echo -e "${YELLOW}⚠${NC} verify_scheduled_jobs.py not found, skipping verification"
fi
echo ""

# Check for errors
echo "Checking for errors in logs..."
if [ -f "docker-compose.prod.yml" ]; then
    ERROR_COUNT=$(docker-compose -f docker-compose.prod.yml logs --tail=100 worker worker2 backend scheduler 2>&1 | grep -i "error" | wc -l)
else
    ERROR_COUNT=$(docker-compose logs --tail=100 worker worker2 backend scheduler 2>&1 | grep -i "error" | wc -l)
fi

if [ "$ERROR_COUNT" -gt 0 ]; then
    echo -e "${YELLOW}⚠${NC} Found $ERROR_COUNT error(s) in logs (check manually)"
else
    echo -e "${GREEN}✓${NC} No errors found in recent logs"
fi
echo ""

# Final summary
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Monitor scheduler logs: docker-compose logs -f scheduler"
echo "2. Verify scheduled jobs execute on time"
echo "3. Test Order Comparison Tool with new timezone"
echo "4. Monitor for 24 hours for any issues"
echo ""
echo "If issues occur, rollback with:"
echo "  git checkout v1.2.0"
echo "  docker-compose restart worker worker2 backend scheduler"
echo ""











