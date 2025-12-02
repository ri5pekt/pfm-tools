# Production Deployment Guide

This guide explains how to safely deploy to production while preserving scheduled jobs and archive data.

## Overview

The deployment process ensures:
- ✅ **Scheduled jobs are preserved** - Jobs stored in database are re-registered automatically
- ✅ **Archive/data is preserved** - Data directory is mounted as volume, not affected by deployment
- ✅ **Environment variables updated** - Workers restarted with new env variables
- ✅ **Zero-downtime deployment** - Rolling restart strategy

## Prerequisites

1. SSH access to production server (`root@31.220.56.146`)
2. SSH key configured for passwordless access
3. Project directory exists on server (default: `/root/pfm-tools`)

## Deployment Methods

### Method 1: Remote Deployment (Recommended)

Deploy from your local machine using SSH:

```bash
bash deploy_production.sh
```

This script:
- Connects to the server via SSH
- Creates backups (database, .env, git tags)
- Verifies scheduled jobs before deployment
- Updates code, environment variables, and restarts services
- Verifies scheduled jobs after deployment

### Method 2: Server-Side Deployment

SSH into the server and run the deployment script directly:

```bash
ssh root@31.220.56.146
cd /root/pfm-tools  # or your project directory
bash deploy_production_server.sh
```

## Deployment Steps

The script automatically performs these steps:

### 1. Pre-deployment Checks
- Verify SSH connection
- Check project directory exists
- Verify docker-compose files

### 2. Create Backups
- **Database backup**: `backups/backup_YYYYMMDD_HHMMSS.sql`
- **Environment file backup**: `.env.backup_YYYYMMDD_HHMMSS`
- **Git tag**: `deployment-backup-YYYYMMDD_HHMMSS`

### 3. Verify Scheduled Jobs (Before)
- List all enabled scheduled jobs from database
- Display job details (name, feature, ID)

### 4. Verify Archive/Data Directory
- Check data directory exists
- Show size and file counts
- Confirm it's mounted as volume (will be preserved)

### 5. Update Environment Variables (Optional)
- Option to update `.env` file
- Existing `.env` is backed up before update

### 6. Update Code
- Pull latest code from git (main/master branch)
- Skip if already on latest commit (unless forced)

### 7. Check Active Jobs
- Check Redis queue for active jobs
- Option to wait for jobs to complete

### 8. Build Docker Images
- Build new images with latest code
- Uses `docker-compose.prod.yml`

### 9. Restart Services (Rolling Restart)
- Restart workers one at a time (zero-downtime)
- Restart backend
- Restart scheduler (re-registers scheduled jobs from database)

### 10. Wait for Initialization
- Wait 30 seconds for services to be ready
- Scheduler needs time to re-register jobs

### 11. Verify Deployment
- Check service status
- Verify scheduled jobs are re-registered
- Check for errors in logs
- Verify archive/data directory is preserved

## Scheduled Jobs Preservation

### How It Works

1. **Database Storage**: Scheduled jobs are stored in `scheduled_exports` table
2. **Automatic Re-registration**: When scheduler restarts, it:
   - Reads all enabled scheduled exports from database
   - Registers them with RQ Scheduler
   - Updates RQ job IDs in database

3. **No Data Loss**: Since jobs are in the database (not in code), they survive deployments

### Verification

After deployment, verify scheduled jobs:

```bash
# On server
docker compose -f docker-compose.prod.yml exec backend python verify_scheduled_jobs.py

# Or via SSH
ssh root@31.220.56.146 'cd /root/pfm-tools && docker compose -f docker-compose.prod.yml exec backend python verify_scheduled_jobs.py'
```

## Archive/Data Directory Preservation

### How It Works

The `data` directory is mounted as a Docker volume in `docker-compose.prod.yml`:

```yaml
volumes:
  - ./data:/data
```

This means:
- ✅ Data persists across container restarts
- ✅ Data persists across deployments
- ✅ No data loss during deployment

### Directory Structure

```
data/
├── processed/    # Processed files and exports
└── uploads/      # Uploaded files
```

## Environment Variables Update

### Before Deployment

1. Prepare your `.env` file locally
2. Include all required variables:
   - Database credentials
   - Redis URL
   - API keys (WooCommerce, Ulta, Shipbob, Zenventory, etc.)
   - Google Sheets credentials
   - Any other service-specific variables

### During Deployment

The script will:
1. Backup existing `.env` file
2. Ask if you want to update environment variables
3. Copy new `.env` file to server (if provided)

### After Deployment

Workers are restarted to pick up new environment variables.

## Monitoring After Deployment

### Immediate Checks (First 30 minutes)

```bash
# Monitor scheduler logs
ssh root@31.220.56.146 'cd /root/pfm-tools && docker compose -f docker-compose.prod.yml logs -f scheduler'

# Check worker logs
ssh root@31.220.56.146 'cd /root/pfm-tools && docker compose -f docker-compose.prod.yml logs -f worker'

# Verify services are running
ssh root@31.220.56.146 'cd /root/pfm-tools && docker compose -f docker-compose.prod.yml ps'
```

### Verify Scheduled Jobs

```bash
ssh root@31.220.56.146 'cd /root/pfm-tools && docker compose -f docker-compose.prod.yml exec backend python verify_scheduled_jobs.py'
```

Expected output:
- ✓ All scheduled jobs listed
- ✓ RQ job IDs match
- ✓ Next run times displayed

### Check for Errors

```bash
ssh root@31.220.56.146 'cd /root/pfm-tools && docker compose -f docker-compose.prod.yml logs --tail=100 | grep -i error'
```

## Rollback Procedure

If deployment causes issues:

### 1. Revert Code

```bash
ssh root@31.220.56.146
cd /root/pfm-tools
git checkout deployment-backup-YYYYMMDD_HHMMSS  # Use backup tag from deployment
```

### 2. Restore Environment (if needed)

```bash
# Restore .env backup
cp .env.backup_YYYYMMDD_HHMMSS .env
```

### 3. Rebuild and Restart

```bash
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml restart worker backend scheduler
```

### 4. Restore Database (if needed)

```bash
# Restore database backup
docker compose -f docker-compose.prod.yml exec -T db psql -U pfmtools pfmtools < backups/backup_YYYYMMDD_HHMMSS.sql
```

## Troubleshooting

### Scheduled Jobs Not Re-registering

```bash
# Check scheduler logs
docker compose -f docker-compose.prod.yml logs scheduler

# Manually trigger scheduler initialization
docker compose -f docker-compose.prod.yml exec scheduler python scheduler.py

# Verify Redis connection
docker compose -f docker-compose.prod.yml exec redis redis-cli ping
```

### Workers Not Starting

```bash
# Check worker logs
docker compose -f docker-compose.prod.yml logs worker

# Verify environment variables
docker compose -f docker-compose.prod.yml exec worker env | grep -E "DATABASE_URL|REDIS_URL"

# Check for configuration errors
docker compose -f docker-compose.prod.yml config
```

### Archive/Data Directory Issues

```bash
# Verify volume is mounted
docker compose -f docker-compose.prod.yml exec backend ls -la /data

# Check directory permissions
docker compose -f docker-compose.prod.yml exec backend ls -la /data/processed
docker compose -f docker-compose.prod.yml exec backend ls -la /data/uploads
```

## Important Notes

1. **Scheduled Jobs Are Safe**: Jobs are stored in database, not code. They survive deployments.

2. **Archive Is Safe**: Data directory is a mounted volume. It persists across deployments.

3. **Environment Variables**: Always update `.env` before restarting workers if you change configuration.

4. **Zero-Downtime**: Rolling restart strategy ensures services stay available during deployment.

5. **Backups**: Always verify backups are created before proceeding with deployment.

## Success Criteria

Deployment is successful when:
- [x] All services are running without errors
- [x] Scheduled jobs are re-registered (check with `verify_scheduled_jobs.py`)
- [x] Next scheduled run executes successfully
- [x] Archive/data directory is intact
- [x] No increase in error logs
- [x] Workers process jobs correctly

## Support

If you encounter issues:
1. Check logs first
2. Verify backups exist
3. Check scheduled jobs status
4. Verify environment variables
5. Review deployment checklist

For critical issues, rollback immediately using the backup tag created during deployment.

