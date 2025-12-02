# Production Deployment - Quick Reference

## Quick Deploy Command

### From Local Machine (Recommended)
```bash
bash deploy_production.sh
```

### From Server (Alternative)
```bash
ssh root@31.220.56.146
cd /root/pfm-tools
bash deploy_production_server.sh
```

## What Gets Preserved

✅ **Scheduled Jobs** - Stored in database, automatically re-registered by scheduler
✅ **Archive/Data** - Mounted volume, persists across deployments
✅ **Database** - Backed up before deployment
✅ **Environment Variables** - Backed up before update

## What Gets Updated

🔄 **Code** - Latest from git (main/master branch)
🔄 **Docker Images** - Rebuilt with latest code
🔄 **Workers** - Restarted with new code and env variables
🔄 **Backend** - Restarted with new code
🔄 **Scheduler** - Restarted (re-registers scheduled jobs)

## Key Verification Commands

### After Deployment
```bash
# Verify scheduled jobs
ssh root@31.220.56.146 'cd /root/pfm-tools && docker compose -f docker-compose.prod.yml exec backend python verify_scheduled_jobs.py'

# Check service status
ssh root@31.220.56.146 'cd /root/pfm-tools && docker compose -f docker-compose.prod.yml ps'

# Monitor logs
ssh root@31.220.56.146 'cd /root/pfm-tools && docker compose -f docker-compose.prod.yml logs -f scheduler'
```

## Rollback

```bash
ssh root@31.220.56.146
cd /root/pfm-tools
git checkout deployment-backup-YYYYMMDD_HHMMSS
docker compose -f docker-compose.prod.yml restart worker backend scheduler
```

## Deployment Flow

1. **Backup** → Database, .env, git tag
2. **Verify** → Scheduled jobs, archive directory
3. **Update** → Code, env variables (optional), Docker images
4. **Restart** → Workers → Backend → Scheduler (rolling)
5. **Verify** → Services, scheduled jobs, logs

## Time Estimate

- Backup: ~2 minutes
- Code update: ~1 minute
- Build images: ~5-10 minutes
- Restart services: ~2 minutes
- Verification: ~1 minute

**Total: ~10-15 minutes**

