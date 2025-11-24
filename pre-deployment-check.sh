#!/bin/bash

# Pre-Deployment Check Script for PFM Tools v1.2.0
# Run this on your production server via SSH

echo "=========================================="
echo "PFM Tools v1.2.0 Pre-Deployment Checks"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check command status
check_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "${RED}✗${NC} $1"
        return 1
    fi
}

# 1. Check current directory
echo "1. Checking current directory..."
if [ -f "docker-compose.prod.yml" ] || [ -f "docker-compose.yml" ]; then
    check_status "Project directory found"
    PROJECT_DIR=$(pwd)
    echo "   Current directory: $PROJECT_DIR"
else
    echo -e "${RED}✗${NC} Not in project directory. Please cd to your pfm-tools directory"
    exit 1
fi
echo ""

# 2. Check Docker and Docker Compose
echo "2. Checking Docker installation..."
if command -v docker &> /dev/null; then
    check_status "Docker is installed"
    docker --version
else
    echo -e "${RED}✗${NC} Docker is not installed"
    exit 1
fi

if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
    check_status "Docker Compose is installed"
    docker-compose --version 2>/dev/null || docker compose version
else
    echo -e "${RED}✗${NC} Docker Compose is not installed"
    exit 1
fi
echo ""

# 3. Check running containers
echo "3. Checking running containers..."
if docker-compose ps 2>/dev/null | grep -q "Up" || docker compose ps 2>/dev/null | grep -q "Up"; then
    check_status "Containers are running"
    echo ""
    echo "Current container status:"
    docker-compose ps 2>/dev/null || docker compose ps
else
    echo -e "${YELLOW}⚠${NC} No containers are currently running"
fi
echo ""

# 4. Check for active jobs in Redis queue
echo "4. Checking Redis queue for active jobs..."
if docker-compose ps redis 2>/dev/null | grep -q "Up" || docker compose ps redis 2>/dev/null | grep -q "Up"; then
    QUEUE_SIZE=$(docker exec $(docker-compose ps -q redis 2>/dev/null || docker compose ps -q redis 2>/dev/null) redis-cli LLEN rq:queue:pfmtools 2>/dev/null || echo "0")
    if [ "$QUEUE_SIZE" -gt 0 ]; then
        echo -e "${YELLOW}⚠${NC} There are $QUEUE_SIZE jobs in the queue"
        echo "   Consider waiting for jobs to complete before deploying"
    else
        check_status "No active jobs in queue (queue is empty)"
    fi
else
    echo -e "${YELLOW}⚠${NC} Redis container is not running - cannot check queue"
fi
echo ""

# 5. Check Git status
echo "5. Checking Git repository status..."
if [ -d ".git" ]; then
    check_status "Git repository found"

    CURRENT_BRANCH=$(git branch --show-current)
    echo "   Current branch: $CURRENT_BRANCH"

    # Check if there are uncommitted changes
    if [ -n "$(git status --porcelain)" ]; then
        echo -e "${YELLOW}⚠${NC} There are uncommitted changes in the repository"
        git status --short
    else
        check_status "Working directory is clean"
    fi

    # Check current commit
    CURRENT_COMMIT=$(git rev-parse --short HEAD)
    CURRENT_MSG=$(git log -1 --pretty=format:"%s")
    echo "   Current commit: $CURRENT_COMMIT"
    echo "   Commit message: $CURRENT_MSG"

    # Check if we're behind origin
    git fetch origin 2>/dev/null
    LOCAL=$(git rev-parse @)
    REMOTE=$(git rev-parse @{u} 2>/dev/null || echo "")

    if [ -n "$REMOTE" ] && [ "$LOCAL" != "$REMOTE" ]; then
        BEHIND=$(git rev-list --count @..@{u} 2>/dev/null || echo "?")
        echo -e "${YELLOW}⚠${NC} Local branch is $BEHIND commit(s) behind origin"
        echo "   Run 'git pull origin main' to update"
    else
        check_status "Local branch is up to date with origin"
    fi
else
    echo -e "${RED}✗${NC} Not a Git repository"
    exit 1
fi
echo ""

# 6. Check for new dependencies
echo "6. Checking for dependency changes..."
if [ -f "backend/requirements.txt" ]; then
    check_status "requirements.txt found"

    # Check if reportlab is in requirements (required for v1.1.0+)
    if grep -q "reportlab" backend/requirements.txt; then
        check_status "reportlab dependency found (required for v1.1.0+)"
    else
        echo -e "${YELLOW}⚠${NC} reportlab not found in requirements.txt (may need to be added)"
    fi
else
    echo -e "${RED}✗${NC} requirements.txt not found"
fi
echo ""

# 7. Check disk space
echo "7. Checking disk space..."
DISK_USAGE=$(df -h . | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 80 ]; then
    check_status "Sufficient disk space available ($DISK_USAGE% used)"
else
    echo -e "${YELLOW}⚠${NC} Disk space is $DISK_USAGE% used - consider cleaning up"
fi
echo ""

# 8. Check Docker images
echo "8. Checking Docker images..."
if docker images | grep -q "pfm-tools"; then
    check_status "PFM Tools Docker images found"
    echo "   Existing images:"
    docker images | grep "pfm-tools" | head -5
else
    echo -e "${YELLOW}⚠${NC} No existing PFM Tools images found (will need to build)"
fi
echo ""

# Summary
echo "=========================================="
echo "Pre-Deployment Check Summary"
echo "=========================================="
echo ""
echo "If all checks passed, you can proceed with deployment:"
echo ""
echo "1. git pull origin main"
echo "2. docker-compose -f docker-compose.prod.yml build"
echo "3. docker-compose -f docker-compose.prod.yml down"
echo "4. docker-compose -f docker-compose.prod.yml up -d --scale worker=2"
echo ""
echo "Or use the regular docker-compose.yml if that's what you use:"
echo "1. git pull origin main"
echo "2. docker-compose build"
echo "3. docker-compose down"
echo "4. docker-compose up -d"
echo ""

