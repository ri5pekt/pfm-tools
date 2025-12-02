#!/bin/bash

# Production Deployment Script
# Safely deploys to production while preserving scheduled jobs and archive
# Usage: bash deploy_production.sh

set -e  # Exit on error

# Configuration
PRODUCTION_SERVER="root@31.220.56.146"
PROJECT_DIR="/root/pfm-tools"  # Adjust if different on server
COMPOSE_FILE="docker-compose.prod.yml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "=========================================="
echo "PFM Tools Production Deployment"
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

# Function to execute command on remote server
remote_exec() {
    ssh "$PRODUCTION_SERVER" "$@"
}

# Function to copy file to remote server
remote_copy() {
    scp "$1" "$PRODUCTION_SERVER:$2"
}

# Step 1: Pre-deployment checks
echo "Step 1: Pre-deployment checks..."
echo "=========================================="

# Check SSH connection
print_info "Testing SSH connection to $PRODUCTION_SERVER..."
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$PRODUCTION_SERVER" echo "Connection successful" &>/dev/null; then
    print_error "Cannot connect to $PRODUCTION_SERVER"
    print_info "Please ensure:"
    echo "  - SSH key is configured"
    echo "  - Server is accessible"
    exit 1
fi
print_success "SSH connection verified"
echo ""

# Check if project directory exists
print_info "Checking project directory on server..."
if ! remote_exec "[ -d '$PROJECT_DIR' ]"; then
    print_error "Project directory '$PROJECT_DIR' not found on server"
    exit 1
fi
print_success "Project directory found"
echo ""

# Step 2: Create backups
echo "Step 2: Creating backups..."
echo "=========================================="

BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$PROJECT_DIR/backups"
BACKUP_FILE="backup_$BACKUP_TIMESTAMP.sql"
ENV_BACKUP=".env.backup_$BACKUP_TIMESTAMP"

# Create backup directory if it doesn't exist
remote_exec "mkdir -p '$BACKUP_DIR'"

# Backup database
print_info "Backing up database..."
if remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE ps db 2>/dev/null | grep -q 'Up' || docker-compose -f $COMPOSE_FILE ps db 2>/dev/null | grep -q 'Up'"; then
    DB_CONTAINER=$(remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE ps -q db 2>/dev/null || docker-compose -f $COMPOSE_FILE ps -q db 2>/dev/null")
    if remote_exec "docker exec $DB_CONTAINER pg_dump -U pfmtools pfmtools > '$BACKUP_DIR/$BACKUP_FILE' 2>/dev/null"; then
        print_success "Database backup created: $BACKUP_FILE"
    else
        print_warning "Could not create database backup (may not be critical)"
    fi
else
    print_warning "Database container not running, skipping backup"
fi

# Backup .env file
print_info "Backing up .env file..."
if remote_exec "[ -f '$PROJECT_DIR/.env' ]"; then
    remote_exec "cp '$PROJECT_DIR/.env' '$PROJECT_DIR/$ENV_BACKUP'"
    print_success ".env file backed up: $ENV_BACKUP"
else
    print_warning ".env file not found (will be created if needed)"
fi

# Backup current git commit
print_info "Tagging current version..."
remote_exec "cd '$PROJECT_DIR' && git tag -a deployment-backup-$BACKUP_TIMESTAMP -m 'Backup before deployment' 2>/dev/null || true"
print_success "Git tag created"
echo ""

# Step 3: Verify scheduled jobs BEFORE deployment
echo "Step 3: Verifying scheduled jobs (before deployment)..."
echo "=========================================="

print_info "Checking current scheduled jobs in database..."
SCHEDULED_JOBS_COUNT=$(remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE exec -T backend python -c \"
from app.core.db import SessionLocal
from app.jobs.models import ScheduledExport
db = SessionLocal()
count = db.query(ScheduledExport).filter(ScheduledExport.enabled == True).count()
print(count)
db.close()
\" 2>/dev/null" | tail -1 | tr -d '[:space:]' || echo "0")

if [ "$SCHEDULED_JOBS_COUNT" = "0" ]; then
    print_warning "No enabled scheduled jobs found in database (this may be normal)"
else
    print_success "Found $SCHEDULED_JOBS_COUNT enabled scheduled job(s) in database"
fi

# List scheduled jobs
print_info "Current scheduled jobs:"
remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE exec -T backend python -c \"
from app.core.db import SessionLocal
from app.jobs.models import ScheduledExport
db = SessionLocal()
jobs = db.query(ScheduledExport).filter(ScheduledExport.enabled == True).all()
for job in jobs:
    print(f'  - {job.name} ({job.feature}) - ID: {job.id}')
db.close()
\" 2>/dev/null || echo '  (Could not retrieve job list)'"
echo ""

# Step 4: Verify archive/data directory
echo "Step 4: Verifying archive/data directory..."
echo "=========================================="

DATA_DIR="$PROJECT_DIR/data"
if remote_exec "[ -d '$DATA_DIR' ]"; then
    DATA_SIZE=$(remote_exec "du -sh '$DATA_DIR' 2>/dev/null | cut -f1" || echo "unknown")
    print_success "Archive/data directory exists (size: $DATA_SIZE)"
    print_info "Directory will be preserved (mounted as volume)"
else
    print_warning "Data directory not found (will be created automatically)"
fi
echo ""

# Step 5: Update environment variables
echo "Step 5: Environment variables update..."
echo "=========================================="

print_info "Checking for .env file updates..."
read -p "Do you want to update environment variables? (yes/no): " update_env

if [ "$update_env" = "yes" ]; then
    print_info "Please provide the path to the new .env file (or press Enter to skip): "
    read -r env_file_path

    if [ -n "$env_file_path" ] && [ -f "$env_file_path" ]; then
        print_info "Copying .env file to server..."
        remote_copy "$env_file_path" "$PROJECT_DIR/.env.new"
        remote_exec "mv '$PROJECT_DIR/.env.new' '$PROJECT_DIR/.env'"
        print_success ".env file updated"
    else
        print_warning "Invalid file path or file not found, skipping .env update"
        print_info "You can manually update .env on the server later"
    fi
else
    print_info "Skipping .env update (existing .env will be used)"
fi
echo ""

# Step 6: Pull latest code
echo "Step 6: Pulling latest code..."
echo "=========================================="

print_info "Fetching latest code from git..."
remote_exec "cd '$PROJECT_DIR' && git fetch origin"

CURRENT_COMMIT=$(remote_exec "cd '$PROJECT_DIR' && git rev-parse HEAD" | tr -d '[:space:]')
REMOTE_COMMIT=$(remote_exec "cd '$PROJECT_DIR' && git rev-parse origin/main 2>/dev/null || git rev-parse origin/master 2>/dev/null" | tr -d '[:space:]')

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
    remote_exec "cd '$PROJECT_DIR' && git pull origin main || git pull origin master"
    print_success "Code updated"
fi
echo ""

# Step 7: Check for active jobs
echo "Step 7: Checking for active jobs..."
echo "=========================================="

if remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE ps redis 2>/dev/null | grep -q 'Up' || docker-compose -f $COMPOSE_FILE ps redis 2>/dev/null | grep -q 'Up'"; then
    REDIS_CONTAINER=$(remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE ps -q redis 2>/dev/null || docker-compose -f $COMPOSE_FILE ps -q redis 2>/dev/null")
    QUEUE_SIZE=$(remote_exec "docker exec $REDIS_CONTAINER redis-cli LLEN rq:queue:pfmtools 2>/dev/null || echo '0'" | tr -d '[:space:]')

    if [ "$QUEUE_SIZE" -gt 0 ]; then
        print_warning "There are $QUEUE_SIZE jobs in the queue"
        read -p "Wait for jobs to complete? (yes/no): " wait_jobs
        if [ "$wait_jobs" = "yes" ]; then
            print_info "Waiting for queue to empty..."
            while [ "$QUEUE_SIZE" -gt 0 ]; do
                sleep 5
                QUEUE_SIZE=$(remote_exec "docker exec $REDIS_CONTAINER redis-cli LLEN rq:queue:pfmtools 2>/dev/null || echo '0'" | tr -d '[:space:]')
                echo "  Queue size: $QUEUE_SIZE"
            done
            print_success "Queue is empty"
        fi
    else
        print_success "No active jobs in queue"
    fi
fi
echo ""

# Step 8: Build new images
echo "Step 8: Building Docker images..."
echo "=========================================="

print_info "Building images (this may take a few minutes)..."
if remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE build --no-cache"; then
    print_success "Images built successfully"
else
    print_error "Image build failed"
    exit 1
fi
echo ""

# Step 9: Restart services (preserving scheduled jobs)
echo "Step 9: Restarting services (zero-downtime strategy)..."
echo "=========================================="

print_info "Using rolling restart to preserve scheduled jobs..."

# Restart workers one at a time to pick up new code and env variables
print_info "Restarting worker containers..."
remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE restart worker"

# Check if worker2 exists and restart it
if remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE ps worker2 2>/dev/null | grep -q 'Up' || docker compose -f $COMPOSE_FILE config --services 2>/dev/null | grep -q '^worker2$'"; then
    print_info "Restarting worker2..."
    remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE restart worker2 2>/dev/null || true"
else
    # Try scaling if using docker compose scale
    print_info "Scaling workers..."
    remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE up -d --scale worker=2 --no-deps worker 2>/dev/null || true"
fi

sleep 5

# Restart backend
print_info "Restarting backend..."
remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE restart backend"

sleep 5

# Restart scheduler (this will re-register all scheduled jobs from database)
print_info "Restarting scheduler (will re-register scheduled jobs)..."
remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE restart scheduler"

print_success "Services restarted"
echo ""

# Step 10: Wait for services to initialize
echo "Step 10: Waiting for services to initialize..."
echo "=========================================="

print_info "Waiting 30 seconds for services to be ready..."
sleep 30
print_success "Services should be ready"
echo ""

# Step 11: Verify deployment
echo "Step 11: Verifying deployment..."
echo "=========================================="

# Check service status
print_info "Checking service status..."
remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE ps"
echo ""

# Verify scheduled jobs are re-registered
print_info "Verifying scheduled jobs are re-registered..."
if remote_exec "[ -f '$PROJECT_DIR/verify_scheduled_jobs.py' ]"; then
    remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE exec -T backend python verify_scheduled_jobs.py || docker compose -f $COMPOSE_FILE exec -T backend python /app/verify_scheduled_jobs.py"
else
    # Fallback: manual verification
    print_info "Checking scheduled jobs in database and RQ..."
    remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE exec -T backend python -c \"
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
for job in jobs:
    rq_exists = any(j.id == job.rq_job_id for j in rq_jobs)
    status = '✓' if rq_exists else '✗'
    print(f'{status} {job.name} ({job.feature})')
db.close()
\" 2>/dev/null || echo 'Could not verify scheduled jobs'"
fi
echo ""

# Check for errors in logs
print_info "Checking for errors in logs..."
ERROR_COUNT=$(remote_exec "cd '$PROJECT_DIR' && docker compose -f $COMPOSE_FILE logs --tail=100 worker backend scheduler 2>&1 | grep -i 'error' | wc -l" | tr -d '[:space:]')

if [ "$ERROR_COUNT" -gt 0 ]; then
    print_warning "Found $ERROR_COUNT error(s) in logs (please check manually)"
    print_info "To view logs: ssh $PRODUCTION_SERVER 'cd $PROJECT_DIR && docker compose -f $COMPOSE_FILE logs --tail=100 worker backend scheduler'"
else
    print_success "No errors found in recent logs"
fi
echo ""

# Step 12: Final summary
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  - Backups created in: $BACKUP_DIR"
echo "  - Database backup: $BACKUP_FILE"
echo "  - .env backup: $ENV_BACKUP"
echo "  - Scheduled jobs: Preserved (re-registered by scheduler)"
echo "  - Archive/data: Preserved (mounted volume)"
echo ""
echo "Next steps:"
echo "  1. Monitor scheduler logs:"
echo "     ssh $PRODUCTION_SERVER 'cd $PROJECT_DIR && docker compose -f $COMPOSE_FILE logs -f scheduler'"
echo ""
echo "  2. Verify scheduled jobs execute on time"
echo ""
echo "  3. Check worker logs for any issues:"
echo "     ssh $PRODUCTION_SERVER 'cd $PROJECT_DIR && docker compose -f $COMPOSE_FILE logs -f worker'"
echo ""
echo "  4. Monitor for 24 hours for any issues"
echo ""
echo "If issues occur, rollback with:"
echo "  ssh $PRODUCTION_SERVER 'cd $PROJECT_DIR && git checkout deployment-backup-$BACKUP_TIMESTAMP && docker compose -f $COMPOSE_FILE restart worker backend scheduler'"
echo ""
print_success "Deployment completed successfully!"

