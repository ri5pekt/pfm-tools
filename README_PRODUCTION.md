# Production Deployment Guide

## Worker Scaling Options

### Option 1: Docker Compose with Fixed Workers (Simple)

**Current approach** - Define workers in `docker-compose.yml`:

```yaml
worker:
  # ... config
worker2:
  # ... config
```

**Pros:**
- Simple and predictable
- Easy to manage
- Good for small to medium workloads

**Cons:**
- Must manually add/remove workers
- Fixed capacity (over-provisioned or under-provisioned)
- Requires docker-compose restart to change

**Best for:** Small teams, predictable workloads, simple deployments

---

### Option 2: Docker Compose with Scaling (Recommended for Docker)

Use `docker-compose scale` to dynamically scale workers:

```bash
# Start with 2 workers
docker-compose up -d --scale worker=2

# Scale up to 5 workers when busy
docker-compose up -d --scale worker=5

# Scale down to 1 worker when quiet
docker-compose up -d --scale worker=1
```

**Pros:**
- Dynamic scaling without code changes
- Easy to adjust based on load
- No need to modify docker-compose.yml

**Cons:**
- Manual scaling (not automatic)
- Need to monitor queue size yourself

**Best for:** Medium deployments, predictable scaling needs

---

### Option 3: Auto-Scaling with Monitoring (Advanced)

Create a simple auto-scaler script that monitors Redis queue size:

```python
# auto_scaler.py
import redis
import subprocess
import time

redis_client = redis.from_url('redis://localhost:6379')
target_workers = 2  # Base number of workers

while True:
    queue_size = redis_client.llen('rq:queue:pfmtools')

    # Scale based on queue size
    if queue_size > 10:
        target_workers = 5
    elif queue_size > 5:
        target_workers = 3
    else:
        target_workers = 2

    # Update docker-compose scale
    subprocess.run(['docker-compose', 'up', '-d', '--scale', f'worker={target_workers}'])

    time.sleep(30)  # Check every 30 seconds
```

**Best for:** Production with variable load

---

### Option 4: Kubernetes / Docker Swarm (Enterprise)

Use orchestration platform with auto-scaling:

**Kubernetes:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: worker
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: worker
        image: your-registry/worker:latest
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: worker-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: worker
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

**Best for:** Large-scale production, cloud deployments

---

### Option 5: Cloud Services (Managed)

**AWS ECS / Fargate:**
- Auto-scaling based on queue depth
- Pay only for what you use
- Managed infrastructure

**Google Cloud Run:**
- Serverless workers
- Auto-scales to zero
- Pay per request

**Best for:** Cloud-native deployments, minimal ops overhead

---

## Recommended Production Setup

### For Small/Medium Scale (Recommended):

1. **Use docker-compose with scaling:**
   ```bash
   # Start with 2-3 workers
   docker-compose up -d --scale worker=3
   ```

2. **Monitor queue size:**
   ```bash
   # Check queue size
   docker exec pfm-tools-redis-1 redis-cli LLEN rq:queue:pfmtools
   ```

3. **Scale manually based on load:**
   - Queue size > 10: Scale to 5 workers
   - Queue size > 5: Scale to 3 workers
   - Queue size < 3: Scale to 2 workers

### For Large Scale:

1. **Use Kubernetes with HPA** (Horizontal Pod Autoscaler)
2. **Or use cloud-managed services** (ECS, Cloud Run)
3. **Implement queue monitoring** and auto-scaling

---

## Environment Variables for Production

Create a `.env.production` file:

```bash
# Worker Configuration
WORKER_COUNT=3
WORKER_CONCURRENCY=1  # Jobs per worker (RQ default is 1)

# Backend Configuration
BACKEND_WORKERS=4  # Uvicorn workers
BACKEND_PORT=8000

# Database
POSTGRES_DB=pfmtools
POSTGRES_USER=pfmtools
POSTGRES_PASSWORD=your_secure_password

# Redis
REDIS_URL=redis://redis:6379/0
```

---

## Monitoring Queue Size

Add this to your monitoring dashboard:

```python
# Check queue size
import redis
r = redis.from_url('redis://localhost:6379')
queue_size = r.llen('rq:queue:pfmtools')
print(f"Jobs in queue: {queue_size}")
```

---

## Best Practices

1. **Start with 2-3 workers** and scale based on actual load
2. **Monitor queue depth** - if it grows, add workers
3. **Set maximum workers** based on your server capacity
4. **Use health checks** to ensure workers are healthy
5. **Implement graceful shutdown** for workers
6. **Log worker metrics** (jobs processed, errors, etc.)

---

## Quick Reference

```bash
# Start with 3 workers
docker-compose up -d --scale worker=3

# Scale to 5 workers
docker-compose up -d --scale worker=5

# Check worker status
docker-compose ps worker

# Check queue size
docker exec pfm-tools-redis-1 redis-cli LLEN rq:queue:pfmtools

# View worker logs
docker-compose logs -f worker
```

