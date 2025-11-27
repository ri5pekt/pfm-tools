# Production Deployment Guide - v1.3.0

## 🎯 Deployment Safety Assessment

### ✅ SAFE TO DEPLOY - No Breaking Changes

**Impact on Scheduled Jobs: ZERO**
- All changes are isolated to `order_comparison` feature
- Scheduled jobs use `inventory_data` and `ulta_marketplace` features (unchanged)
- No database schema changes
- All function signatures are backward compatible

### Changes Summary

| Component | Change | Impact on Scheduled Jobs |
|-----------|--------|-------------------------|
| `order_comparison` service | Timezone fix, country filtering | ✅ None (not used by scheduled jobs) |
| `order_comparison` worker | Progress bar updates | ✅ None (not used by scheduled jobs) |
| Database models | No changes | ✅ None |
| Scheduler | No changes | ✅ None |
| `inventory_data` | No changes | ✅ None |
| `ulta_marketplace` | No changes | ✅ None |

## 📋 Pre-Deployment Checklist

### 1. Backup (5 minutes)
```bash
# Backup database
docker-compose exec db pg_dump -U pfmtools pfmtools > backup_$(date +%Y%m%d_%H%M%S).sql

# Tag current version
git tag v1.2.0-backup-$(date +%Y%m%d)
```

### 2. Verify Scheduled Jobs (2 minutes)
```bash
# Run pre-deployment check
bash pre-deployment-check.sh

# Or manually check
docker-compose exec backend python verify_scheduled_jobs.py
```

### 3. Update WooCommerce Plugin FIRST ⚠️
**CRITICAL**: Plugin must be updated BEFORE backend deployment

1. Upload `pfm-tools-utils-woocommerce-plugin-mirror/pfm-tools-utils.php` to WordPress
2. Verify plugin is active
3. Test API endpoint:
   ```bash
   curl -u "ck_597bfb235fcc35a4386fbe0c34fd7e72def53b20:cs_2f9188de18d63a3b1a3d937b84400e263c937c1b" \
     "https://www.particleformen.com/wp-json/pfm-tools/v1/orders?date_after=2025-10-02%2000:00:00&date_before=2025-10-02%2023:59:59&per_page=10&page=1"
   ```

### 4. Deploy Backend Code (10 minutes)

#### Option A: Zero-Downtime Rolling Restart (Recommended)
```bash
# 1. Pull latest code
git pull origin main
git log -1 --oneline  # Verify: 48c92d8

# 2. Build new images
docker-compose -f docker-compose.prod.yml build

# 3. Restart workers one at a time
docker-compose -f docker-compose.prod.yml restart worker
sleep 10
docker-compose -f docker-compose.prod.yml restart worker2
sleep 10

# 4. Restart backend (auto-reloads, but restart to be safe)
docker-compose -f docker-compose.prod.yml restart backend

# 5. Restart scheduler (will re-register all scheduled jobs)
docker-compose -f docker-compose.prod.yml restart scheduler
```

#### Option B: Full Restart (Faster, brief downtime)
```bash
# 1. Pull latest code
git pull origin main

# 2. Build and restart
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d --scale worker=2
```

### 5. Post-Deployment Verification (5 minutes)

```bash
# Wait for scheduler to initialize (30 seconds)
sleep 30

# Verify scheduled jobs re-registered
docker-compose exec backend python verify_scheduled_jobs.py

# Check scheduler logs
docker-compose logs scheduler --tail=50 | grep -i "scheduled export"

# Verify all services running
docker-compose ps

# Check for errors
docker-compose logs --tail=100 worker worker2 backend scheduler | grep -i error
```

## 🔍 What to Monitor

### First 30 Minutes
- [ ] Scheduler re-registers all scheduled jobs
- [ ] No errors in worker logs
- [ ] No errors in scheduler logs
- [ ] Scheduled jobs execute on time

### First 24 Hours
- [ ] All scheduled exports complete successfully
- [ ] Order comparison tool works with new timezone
- [ ] Progress bar shows accurate percentages (5-95% for WooCommerce)
- [ ] Country filtering works correctly
- [ ] No increase in error rates

## 🚨 Rollback Plan

If issues occur:

```bash
# 1. Revert code
git checkout v1.2.0
# OR
git revert 48c92d8

# 2. Revert plugin (upload old version to WordPress)
# Change METORIK_TZ back to 'America/New_York'

# 3. Restart services
docker-compose -f docker-compose.prod.yml restart worker worker2 backend scheduler

# 4. Restore database (if needed)
docker-compose exec -T db psql -U pfmtools pfmtools < backup_YYYYMMDD_HHMMSS.sql
```

## ✅ Success Criteria

Deployment is successful when:
- [x] All services running without errors
- [x] Scheduled jobs re-registered (check with `verify_scheduled_jobs.py`)
- [x] Next scheduled run executes successfully
- [x] Order comparison tool works with UTC timezone
- [x] Country filtering works correctly
- [x] Progress bar shows accurate percentages

## 📝 Notes

- **Scheduled jobs are SAFE**: They use `inventory_data` and `ulta_marketplace` features which are unchanged
- **No database migration needed**: All changes are code-only
- **Backward compatible**: All function signatures maintain compatibility
- **Plugin update is critical**: Must be done before backend deployment

## 🆘 Troubleshooting

### Scheduled Jobs Not Re-registering
```bash
# Check scheduler logs
docker-compose logs scheduler

# Manually trigger scheduler initialization
docker-compose exec scheduler python scheduler.py

# Verify Redis connection
docker-compose exec redis redis-cli ping
```

### Order Comparison Tool Issues
```bash
# Verify plugin is updated
# Check plugin timezone setting in WordPress

# Test API endpoint
curl -u "key:secret" "https://www.particleformen.com/wp-json/pfm-tools/v1/orders?date_after=2025-10-02%2000:00:00&date_before=2025-10-02%2023:59:59&per_page=10&page=1"
```

### Worker Errors
```bash
# Check worker logs
docker-compose logs worker worker2 --tail=100

# Restart workers
docker-compose restart worker worker2
```

