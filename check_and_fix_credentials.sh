#!/bin/bash

echo "=========================================="
echo "Checking Google Sheets Credentials Setup"
echo "=========================================="
echo ""

# Check if credentials exist on host
echo "1. Checking credentials on host..."
if [ -f "backend/credentials/client_secret_google_sheets.json" ] && [ -f "backend/credentials/google_sheets_token.pickle" ]; then
    echo "✓ Credentials files exist on host"
    ls -la backend/credentials/
else
    echo "✗ Credentials files missing on host!"
    exit 1
fi
echo ""

# Check credentials in backend container
echo "2. Checking credentials in backend container..."
if docker compose -f docker-compose.prod.yml exec -T backend test -f /app/credentials/client_secret_google_sheets.json 2>/dev/null; then
    echo "✓ Credentials exist in backend container"
    docker compose -f docker-compose.prod.yml exec -T backend ls -la /app/credentials/
else
    echo "✗ Credentials missing in backend container!"
fi
echo ""

# Check credentials in worker containers
echo "3. Checking credentials in worker containers..."
for worker_num in 1 2 3; do
    worker_name="pfm-tools-worker-${worker_num}"
    if docker ps --format "{{.Names}}" | grep -q "^${worker_name}$"; then
        echo "Checking ${worker_name}..."
        if docker exec ${worker_name} test -f /app/credentials/google_sheets_token.pickle 2>/dev/null; then
            echo "  ✓ Credentials exist in ${worker_name}"
        else
            echo "  ✗ Credentials MISSING in ${worker_name}"
            echo "  Copying credentials to ${worker_name}..."
            docker cp backend/credentials/client_secret_google_sheets.json ${worker_name}:/app/credentials/client_secret_google_sheets.json 2>/dev/null
            docker cp backend/credentials/google_sheets_token.pickle ${worker_name}:/app/credentials/google_sheets_token.pickle 2>/dev/null
            if docker exec ${worker_name} test -f /app/credentials/google_sheets_token.pickle 2>/dev/null; then
                echo "  ✓ Credentials copied successfully"
            else
                echo "  ✗ Failed to copy credentials"
            fi
        fi
    fi
done
echo ""

# Check environment variables
echo "4. Checking environment variables..."
docker compose -f docker-compose.prod.yml exec -T backend env | grep -E "GOOGLE_SHEETS|ULTA_GOOGLE|INVENTORY_GOOGLE" | head -10
echo ""

echo "=========================================="
echo "Summary"
echo "=========================================="
echo "If credentials were missing, they have been copied."
echo "You may need to restart workers for changes to take effect:"
echo "  docker compose -f docker-compose.prod.yml restart worker"
echo ""

