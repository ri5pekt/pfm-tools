#!/bin/bash
# Diagnostic script for PFM Tools deployment issues

echo "=== Checking Docker Containers ==="
docker compose -f docker-compose.prod.yml ps -a

echo -e "\n=== Backend Logs (last 50 lines) ==="
docker compose -f docker-compose.prod.yml logs backend --tail=50

echo -e "\n=== Frontend Logs ==="
docker compose -f docker-compose.prod.yml logs frontend --tail=30

echo -e "\n=== Checking .env file ==="
if [ -f .env ]; then
    echo ".env file exists"
    echo "First 10 lines:"
    head -10 .env
    echo -e "\nChecking for required variables:"
    grep -E "(SECRET_KEY|DATABASE_URL|POSTGRES_PASSWORD)" .env || echo "Missing required variables!"
else
    echo "ERROR: .env file not found!"
fi

echo -e "\n=== Testing Database Connection ==="
docker compose -f docker-compose.prod.yml exec -T db psql -U pfmtools -d pfmtools -c "SELECT 1;" 2>&1 || echo "Database connection failed"

echo -e "\n=== Checking Backend Environment Variables ==="
docker compose -f docker-compose.prod.yml exec -T backend env 2>&1 | grep -E "(DATABASE|SECRET|REDIS|CORS)" || echo "Backend container not accessible"

echo -e "\n=== Network Status ==="
docker network ls | grep pfm-tools

echo -e "\n=== Port Status ==="
netstat -tuln | grep -E "(8000|80|5432|6379)" || ss -tuln | grep -E "(8000|80|5432|6379)"

