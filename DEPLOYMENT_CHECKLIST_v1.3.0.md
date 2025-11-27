# Deployment Checklist - v1.3.0

## Pre-Deployment Verification

### ✅ Changes Summary
- **Order Comparison Tool**: Timezone fix, country filtering, progress bar improvements
- **No database schema changes**: All changes are code-only
- **No breaking changes**: All function signatures maintain backward compatibility
- **Scheduled jobs unaffected**: Changes only affect `order_comparison` feature, not `inventory_data` or `ulta_marketplace`

### ✅ Backward Compatibility Check

#### Function Signatures (All Backward Compatible)
1. `parse_complyt_csv()` - Added optional `usa_only` parameter (defaults to `False`)
2. `fetch_woocommerce_orders()` - No signature changes
3. `run_comparison_job()` - No signature changes

#### Database Models
- ✅ No changes to `Job` model
- ✅ No changes to `ScheduledExport` model
- ✅ No new tables required
- ✅ No column changes required

### ✅ Scheduled Jobs Impact Assessment

**Scheduled jobs use these features:**
- `inventory_data` - ✅ **NOT AFFECTED** (no changes)
- `ulta_marketplace` - ✅ **NOT AFFECTED** (no changes)

**Order Comparison Tool:**
- Only used via manual uploads (not scheduled)
- Changes are isolated to this feature only

## Deployment Steps

### 1. Pre-Deployment Backup
```bash
# Backup database
docker-compose exec db pg_dump -U pfmtools pfmtools > backup_$(date +%Y%m%d_%H%M%S).sql

# Backup current code (if using git)
git tag v1.2.0-backup-$(date +%Y%m%d)
```

### 2. Verify Current Scheduled Jobs
```bash
# Check active scheduled exports
docker-compose exec backend python -c "
from app.core.db import SessionLocal
from app.jobs.models import ScheduledExport
db = SessionLocal()
jobs = db.query(ScheduledExport).filter(ScheduledExport.enabled == True).all()
print(f'Active scheduled jobs: {len(jobs)}')
for job in jobs:
    print(f'  - {job.name} ({job.feature}) - RQ Job ID: {job.rq_job_id}')
db.close()
"
```

### 3. Pull Latest Code
```bash
git pull origin main
# Verify you're on commit 48c92d8 (v1.3.0)
git log -1 --oneline
```

### 4. Update WooCommerce Plugin (CRITICAL)
⚠️ **IMPORTANT**: The plugin timezone change must be deployed to WordPress BEFORE deploying backend code.

```bash
# Upload to WordPress:
# pfm-tools-utils-woocommerce-plugin-mirror/pfm-tools-utils.php
# 
# Key change: Line 33 - METORIK_TZ changed from 'America/New_York' to 'UTC'
# 
# After upload, verify plugin is active and test API endpoint:
curl -u "ck_597bfb235fcc35a4386fbe0c34fd7e72def53b20:cs_2f9188de18d63a3b1a3d937b84400e263c937c1b" \
  "https://www.particleformen.com/wp-json/pfm-tools/v1/orders?date_after=2025-10-02%2000:00:00&date_before=2025-10-02%2023:59:59&per_page=10&page=1"
```

### 5. Restart Services (Zero-Downtime Strategy)

#### Option A: Rolling Restart (Recommended)
```bash
# Restart workers one at a time to avoid job interruption
docker-compose restart worker
sleep 10
docker-compose restart worker2
sleep 10

# Restart backend (has --reload, should auto-reload)
docker-compose restart backend

# Restart scheduler (will re-register all scheduled jobs)
docker-compose restart scheduler
```

#### Option B: Full Restart (Faster, but brief downtime)
```bash
# Stop services
docker-compose stop worker worker2 backend scheduler

# Start services
docker-compose up -d worker worker2 backend scheduler

# Verify all services are running
docker-compose ps
```

### 6. Verify Scheduled Jobs Re-registered
```bash
# Wait 30 seconds for scheduler to initialize
sleep 30

# Check scheduler logs
docker-compose logs scheduler --tail=50 | grep -i "scheduled export"

# Verify RQ jobs are registered
docker-compose exec redis redis-cli ZRANGE rq:scheduler:scheduled_jobs 0 -1
```

### 7. Post-Deployment Verification

#### Test Order Comparison Tool
```bash
# Create a test job via API or UI
# Verify:
# - Progress bar shows correct percentages (5-95% for WooCommerce fetching)
# - Country filtering works when "USA orders only" is checked
# - Orders match correctly between Complyt and WooCommerce
```

#### Verify Scheduled Jobs Still Running
```bash
# Check scheduled jobs are still active
docker-compose exec backend python -c "
from app.core.db import SessionLocal
from app.jobs.models import ScheduledExport
db = SessionLocal()
jobs = db.query(ScheduledExport).filter(ScheduledExport.enabled == True).all()
for job in jobs:
    print(f'{job.name}: enabled={job.enabled}, rq_job_id={job.rq_job_id}')
db.close()
"

# Monitor next scheduled run
docker-compose logs -f scheduler worker worker2
```

#### Check Service Health
```bash
# All services should be running
docker-compose ps

# Check for errors in logs
docker-compose logs --tail=100 worker worker2 backend scheduler | grep -i error
```

## Rollback Plan

If issues occur, rollback immediately:

```bash
# 1. Revert code
git checkout v1.2.0
# OR
git revert 48c92d8

# 2. Revert plugin (upload old version to WordPress)
# Change METORIK_TZ back to 'America/New_York' in plugin

# 3. Restart services
docker-compose restart worker worker2 backend scheduler

# 4. Restore database (if needed)
docker-compose exec -T db psql -U pfmtools pfmtools < backup_YYYYMMDD_HHMMSS.sql
```

## Risk Assessment

### Low Risk ✅
- **Scheduled Jobs**: No code changes affect scheduled job functionality
- **Database**: No schema changes required
- **API Compatibility**: All changes are backward compatible

### Medium Risk ⚠️
- **WooCommerce Plugin**: Must be updated before backend deployment
- **Timezone Change**: Could affect existing in-progress jobs (but unlikely as jobs are date-specific)

### Mitigation
1. Deploy plugin first, verify it works
2. Deploy backend code during low-traffic period
3. Monitor logs for first 30 minutes after deployment
4. Have rollback plan ready

## Monitoring After Deployment

Monitor these for 24 hours:
- ✅ Scheduled jobs execute on time
- ✅ Order comparison jobs complete successfully
- ✅ No increase in error rates
- ✅ Progress bar shows accurate percentages
- ✅ Country filtering works correctly

## Success Criteria

Deployment is successful when:
- [ ] All services running without errors
- [ ] Scheduled jobs re-registered and executing
- [ ] Order comparison tool works with new timezone
- [ ] Country filtering works correctly
- [ ] Progress bar shows accurate percentages
- [ ] No increase in error logs

