# Production Deployment Guide

## Quick Deployment Steps

### 1. Pull Latest Code
```bash
ssh root@31.220.56.146
cd /root/pfm-tools
git pull
```

### 2. Rebuild Frontend (with correct API URL)
```bash
docker compose -f docker-compose.prod.yml build --no-cache --build-arg VITE_API_BASE_URL=/api frontend
```

### 3. Rebuild Backend (if needed)
```bash
docker compose -f docker-compose.prod.yml build backend
```

### 4. Restart Services
```bash
# Stop and remove old frontend container
docker stop pfm-tools-frontend-1 && docker rm pfm-tools-frontend-1

# Start frontend (on correct network)
docker run -d --name pfm-tools-frontend-1 --network pfm-tools_default -p 8080:80 --restart unless-stopped pfm-tools-frontend:latest

# Restart backend
docker compose -f docker-compose.prod.yml restart backend

# Restart workers
docker compose -f docker-compose.prod.yml restart worker worker2

# Restart scheduler (will auto-re-register scheduled jobs)
docker compose -f docker-compose.prod.yml restart scheduler
```

### 5. Verify
```bash
# Check containers
docker ps | grep pfm-tools

# Test API proxy
curl http://localhost:8080/api/health

# Check scheduled jobs
docker compose -f docker-compose.prod.yml exec backend python -c "
from app.core.db import SessionLocal
from app.jobs.models import ScheduledExport
db = SessionLocal()
jobs = db.query(ScheduledExport).filter(ScheduledExport.enabled == True).all()
print(f'{len(jobs)} enabled scheduled jobs')
db.close()
"
```

## Important Notes

### Frontend Build
- **Always** use `--build-arg VITE_API_BASE_URL=/api` when building frontend for production
- The frontend must be on the `pfm-tools_default` network to reach backend via `pfm-tools-backend-1:8000`
- Nginx proxies `/api` requests to the backend container

### Ports
- **Backend**: Port 8000 (production)
- **Frontend**: Port 8080 (production)
- **Dev**: Backend 8001, Frontend 5173

### Scheduled Jobs
- Scheduler automatically re-registers scheduled jobs on restart
- No manual intervention needed

### Browser Cache
- Users may need to hard refresh (Ctrl+F5) to get latest frontend code
- Index.html has cache-busting headers, but JS bundles may be cached

## Common Issues

### Frontend shows old version
- Clear browser cache or hard refresh (Ctrl+F5)
- Verify build timestamp: `docker exec pfm-tools-frontend-1 ls -la /usr/share/nginx/html/assets/`

### Login fails with ERR_CONNECTION_REFUSED
- Check frontend is on correct network: `docker inspect pfm-tools-frontend-1 | grep NetworkMode`
- Verify nginx proxy: `docker exec pfm-tools-frontend-1 cat /etc/nginx/conf.d/default.conf | grep proxy_pass`
- Test backend directly: `curl http://localhost:8000/api/health`
- Test proxy: `curl http://localhost:8080/api/health`

### Missing .env file warning
- This is expected if .env is not in git (for security)
- Services use environment variables from docker-compose or container configs

