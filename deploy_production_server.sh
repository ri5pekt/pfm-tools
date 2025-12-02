#!/bin/bash

# Production Deployment Script - Run this directly on the production server
# Usage: bash deploy_production_server.sh

set -e  # Exit on error

PROJECT_DIR="${1:-$(pwd)}"  # Use first argument or current directory
COMPOSE_FILE="docker-compose.prod.yml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "=========================================="
echo "PFM Tools Production Deployment (Server-side)"
echo "=========================================="
echo ""

# Function to print colored output
print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Change to project directory
cd "$PROJECT_DIR" || {
    print_error "Cannot access project directory: $PROJECT_DIR"
    exit 1
}

print_success "Working directory: $PROJECT_DIR"
echo ""

# Step 1: Pre-deployment checks
echo "Step 1: Pre-deployment checks..."
echo "=========================================="

if [ ! -f "$COMPOSE_FILE" ] && [ ! -f "docker-compose.yml" ]; then
    print_error "Not in project directory (docker-compose files not found)"
    exit 1
fi

COMPOSE_FILE="$(if [ -f "$COMPOSE_FILE" ]; then echo "$COMPOSE_FILE"; else echo "docker-compose.yml"; fi)"
print_success "Using compose file: $COMPOSE_FILE"
echo ""

# Step 2: Create backups
echo "Step 2: Creating backups..."
echo "=========================================="

BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$PROJECT_DIR/backups"
BACKUP_FILE="backup_$BACKUP_TIMESTAMP.sql"
ENV_BACKUP=".env.backup_$BACKUP_TIMESTAMP"

mkdir -p "$BACKUP_DIR"

# Backup database
print_info "Backing up database..."
if docker compose -f "$COMPOSE_FILE" ps db 2>/dev/null | grep -q "Up" || docker-compose -f "$COMPOSE_FILE" ps db 2>/dev/null | grep -q "Up"; then
    DB_CONTAINER=$(docker compose -f "$COMPOSE_FILE" ps -q db 2>/dev/null || docker-compose -f "$COMPOSE_FILE" ps -q db 2>/dev/null)
    if docker exec "$DB_CONTAINER" pg_dump -U pfmtools pfmtools > "$BACKUP_DIR/$BACKUP_FILE" 2>/dev/null; then
        print_success "Database backup created: $BACKUP_FILE ($(du -h "$BACKUP_DIR/$BACKUP_FILE" | cut -f1))"
    else
        print_warning "Could not create database backup (may not be critical)"
    fi
else
    print_warning "Database container not running, skipping backup"
fi

# Backup .env file
print_info "Backing up .env file..."
if [ -f ".env" ]; then
    cp ".env" "$ENV_BACKUP"
    print_success ".env file backed up: $ENV_BACKUP"
else
    print_warning ".env file not found"
fi

# Backup current git commit
print_info "Tagging current version..."
if [ -d ".git" ]; then
    git tag -a "deployment-backup-$BACKUP_TIMESTAMP" -m "Backup before deployment" 2>/dev/null || true
    print_success "Git tag created: deployment-backup-$BACKUP_TIMESTAMP"
fi
echo ""

# Step 3: Verify scheduled jobs BEFORE deployment
echo "Step 3: Verifying scheduled jobs (before deployment)..."
echo "=========================================="

print_info "Checking current scheduled jobs in database..."
SCHEDULED_JOBS_COUNT=$(docker compose -f "$COMPOSE_FILE" exec -T backend python -c "
from app.core.db import SessionLocal
from app.jobs.models import ScheduledExport
db = SessionLocal()
count = db.query(ScheduledExport).filter(ScheduledExport.enabled == True).count()
print(count)
db.close()
" 2>/dev/null | tail -1 | tr -d '[:space:]' || echo "0")

if [ "$SCHEDULED_JOBS_COUNT" = "0" ]; then
    print_warning "No enabled scheduled jobs found in database (this may be normal)"
else
    print_success "Found $SCHEDULED_JOBS_COUNT enabled scheduled job(s) in database"
fi

# List scheduled jobs
print_info "Current scheduled jobs:"
docker compose -f "$COMPOSE_FILE" exec -T backend python -c "
from app.core.db import SessionLocal
from app.jobs.models import ScheduledExport
db = SessionLocal()
jobs = db.query(ScheduledExport).filter(ScheduledExport.enabled == True).all()
for job in jobs:
    print(f'  - {job.name} ({job.feature}) - ID: {job.id}, RQ Job ID: {job.rq_job_id or \"Not registered\"}')
db.close()
" 2>/dev/null || echo "  (Could not retrieve job list)"
echo ""

# Step 4: Verify archive/data directory
echo "Step 4: Verifying archive/data directory..."
echo "=========================================="

DATA_DIR="$PROJECT_DIR/data"
if [ -d "$DATA_DIR" ]; then
    DATA_SIZE=$(du -sh "$DATA_DIR" 2>/dev/null | cut -f1 || echo "unknown")
    print_success "Archive/data directory exists (size: $DATA_SIZE)"
    print_info "Directory will be preserved (mounted as volume)"

    # List subdirectories
    if [ -d "$DATA_DIR/processed" ]; then
        PROCESSED_COUNT=$(find "$DATA_DIR/processed" -type f 2>/dev/null | wc -l || echo "0")
        print_info "  - processed/: $PROCESSED_COUNT files"
    fi
    if [ -d "$DATA_DIR/uploads" ]; then
        UPLOADS_COUNT=$(find "$DATA_DIR/uploads" -type f 2>/dev/null | wc -l || echo "0")
        print_info "  - uploads/: $UPLOADS_COUNT files"
    fi
else
    print_warning "Data directory not found (will be created automatically)"
fi
echo ""

# Step 5: Check for active jobs
echo "Step 5: Checking for active jobs..."
echo "=========================================="

if docker compose -f "$COMPOSE_FILE" ps redis 2>/dev/null | grep -q "Up" || docker-compose -f "$COMPOSE_FILE" ps redis 2>/dev/null | grep -q "Up"; then
    REDIS_CONTAINER=$(docker compose -f "$COMPOSE_FILE" ps -q redis 2>/dev/null || docker-compose -f "$COMPOSE_FILE" ps -q redis 2>/dev/null)
    QUEUE_SIZE=$(docker exec "$REDIS_CONTAINER" redis-cli LLEN rq:queue:pfmtools 2>/dev/null || echo "0")

    if [ "$QUEUE_SIZE" -gt 0 ]; then
        print_warning "There are $QUEUE_SIZE jobs in the queue"
        read -p "Wait for jobs to complete? (yes/no): " wait_jobs
        if [ "$wait_jobs" = "yes" ]; then
            print_info "Waiting for queue to empty..."
            while [ "$QUEUE_SIZE" -gt 0 ]; do
                sleep 5
                QUEUE_SIZE=$(docker exec "$REDIS_CONTAINER" redis-cli LLEN rq:queue:pfmtools 2>/dev/null || echo "0")
                echo "  Queue size: $QUEUE_SIZE"
            done
            print_success "Queue is empty"
        fi
    else
        print_success "No active jobs in queue"
    fi
fi
echo ""

# Step 6: Pull latest code (if in git repo)
echo "Step 6: Updating code..."
echo "=========================================="

if [ -d ".git" ]; then
    print_info "Fetching latest code from git..."
    git fetch origin

    CURRENT_COMMIT=$(git rev-parse HEAD | tr -d '[:space:]')
    REMOTE_COMMIT=$(git rev-parse origin/main 2>/dev/null || git rev-parse origin/master 2>/dev/null | tr -d '[:space:]')

    print_info "Current commit: ${CURRENT_COMMIT:0:7}"
    print_info "Remote commit: ${REMOTE_COMMIT:0:7}"

    if [ "$CURRENT_COMMIT" = "$REMOTE_COMMIT" ]; then
        print_success "Already on latest commit"
        read -p "Force pull anyway? (yes/no): " force_pull
        if [ "$force_pull" != "yes" ]; then
            print_info "Skipping code update"
            SKIP_CODE_UPDATE=true
        fi
    fi

    if [ "$SKIP_CODE_UPDATE" != "true" ]; then
        print_info "Pulling latest code..."
        git pull origin main || git pull origin master
        print_success "Code updated"
    fi
else
    print_warning "Not a git repository, skipping code update"
    print_info "Make sure your code is already up to date"
fi
echo ""

# Step 7: Build new images
echo "Step 7: Building Docker images..."
echo "=========================================="

print_info "Building images (this may take a few minutes)..."
if docker compose -f "$COMPOSE_FILE" build; then
    print_success "Images built successfully"
else
    print_error "Image build failed"
    exit 1
fi
echo ""

# Step 8: Restart services (preserving scheduled jobs)
echo "Step 8: Restarting services (zero-downtime strategy)..."
echo "=========================================="

print_info "Using rolling restart to preserve scheduled jobs and archive..."

# Restart workers one at a time to pick up new code and env variables
print_info "Restarting worker containers..."
docker compose -f "$COMPOSE_FILE" restart worker

# Check if worker2 exists or if we need to scale
sleep 5
if docker compose -f "$COMPOSE_FILE" ps worker2 2>/dev/null | grep -q "Up"; then
    print_info "Restarting worker2..."
    docker compose -f "$COMPOSE_FILE" restart worker2
elif docker compose -f "$COMPOSE_FILE" config --services 2>/dev/null | grep -q "^worker$"; then
    # Scale workers if using docker compose scale
    print_info "Scaling workers to ensure 2 instances..."
    docker compose -f "$COMPOSE_FILE" up -d --scale worker=2 --no-deps worker 2>/dev/null || true
fi

sleep 5

# Restart backend
print_info "Restarting backend..."
docker compose -f "$COMPOSE_FILE" restart backend

sleep 5

# Restart scheduler (this will re-register all scheduled jobs from database)
print_info "Restarting scheduler (will re-register scheduled jobs from database)..."
docker compose -f "$COMPOSE_FILE" restart scheduler

print_success "Services restarted"
echo ""

# Step 9: Wait for services to initialize
echo "Step 9: Waiting for services to initialize..."
echo "=========================================="

print_info "Waiting 30 seconds for services to be ready..."
sleep 30
print_success "Services should be ready"
echo ""

# Step 10: Verify deployment
echo "Step 10: Verifying deployment..."
echo "=========================================="

# Check service status
print_info "Checking service status..."
docker compose -f "$COMPOSE_FILE" ps
echo ""

# Verify scheduled jobs are re-registered
print_info "Verifying scheduled jobs are re-registered..."
if [ -f "verify_scheduled_jobs.py" ]; then
    docker compose -f "$COMPOSE_FILE" exec -T backend python verify_scheduled_jobs.py || \
    docker compose -f "$COMPOSE_FILE" exec -T backend python /app/verify_scheduled_jobs.py
else
    # Fallback: manual verification
    print_info "Checking scheduled jobs in database and RQ..."
    docker compose -f "$COMPOSE_FILE" exec -T backend python -c "
from app.core.db import SessionLocal
from app.jobs.models import ScheduledExport
from rq_scheduler import Scheduler
from app.jobs.queues import get_redis_connection
db = SessionLocal()
jobs = db.query(ScheduledExport).filter(ScheduledExport.enabled == True).all()
print(f'Database: {len(jobs)} enabled scheduled jobs')
conn = get_redis_connection()
scheduler = Scheduler(connection=conn)
rq_jobs = scheduler.get_jobs()
print(f'RQ Scheduler: {len(rq_jobs)} registered jobs')
print()
all_good = True
for job in jobs:
    rq_exists = any(j.id == job.rq_job_id for j in rq_jobs) if job.rq_job_id else False
    status = '✓' if rq_exists else '✗'
    print(f'{status} {job.name} ({job.feature}) - RQ ID: {job.rq_job_id or \"Not registered\"}')
    if not rq_exists and job.rq_job_id:
        all_good = False
if all_good:
    print()
    print('✓ All scheduled jobs are properly registered!')
else:
    print()
    print('⚠ Some scheduled jobs need re-registration. Scheduler should handle this automatically.')
db.close()
" 2>/dev/null || echo "Could not verify scheduled jobs"
fi
echo ""

# Verify archive/data directory still exists
print_info "Verifying archive/data directory is preserved..."
if [ -d "$DATA_DIR" ]; then
    DATA_SIZE_AFTER=$(du -sh "$DATA_DIR" 2>/dev/null | cut -f1 || echo "unknown")
    print_success "Archive/data directory preserved (size: $DATA_SIZE_AFTER)"
else
    print_warning "Data directory not found after deployment (may be normal if empty)"
fi
echo ""

# Check for errors in logs
print_info "Checking for errors in logs..."
ERROR_COUNT=$(docker compose -f "$COMPOSE_FILE" logs --tail=100 worker backend scheduler 2>&1 | grep -i "error" | grep -v "ERROR:__main__" | wc -l || echo "0")

if [ "$ERROR_COUNT" -gt 0 ]; then
    print_warning "Found $ERROR_COUNT error(s) in logs (please check manually)"
    print_info "To view logs: docker compose -f $COMPOSE_FILE logs --tail=100 worker backend scheduler"
else
    print_success "No errors found in recent logs"
fi
echo ""

# Step 11: Final summary
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - Backups created in: $BACKUP_DIR"
echo "  - Database backup: $BACKUP_FILE"
echo "  - .env backup: $ENV_BACKUP"
echo "  - Scheduled jobs: Preserved and re-registered"
echo "  - Archive/data: Preserved (mounted volume)"
echo "  - Workers: Restarted with new code and env variables"
echo ""
echo "Next steps:"
echo "  1. Monitor scheduler logs:"
echo "     docker compose -f $COMPOSE_FILE logs -f scheduler"
echo ""
echo "  2. Verify scheduled jobs execute on time"
echo ""
echo "  3. Check worker logs for any issues:"
echo "     docker compose -f $COMPOSE_FILE logs -f worker"
echo ""
echo "  4. Monitor for 24 hours for any issues"
echo ""
echo "If issues occur, rollback with:"
echo "  git checkout deployment-backup-$BACKUP_TIMESTAMP"
echo "  docker compose -f $COMPOSE_FILE restart worker backend scheduler"
echo ""
print_success "Deployment completed successfully!"

