# PFM Tools

**Version:** 1.6.4

A modern web application for processing sales tax data, managing inventory, and exporting marketplace data with integration to WooCommerce, Braintree, AfterShip, Ulta Marketplace, Zenventory, ShipBob, and Google Sheets.

## 📝 Changelog

### Version 1.4.0 (2025-11-30)
- **Ulta Marketplace Tool Enhancements**:
  - Added "Total Daily Refunds" column (Column G) to both CSV and Google Sheets exports
  - Refunds are grouped by order date (not refund date) for accurate daily tracking
  - Refunds display total refund amount in dollars
  - Auto-generate month+year tab names for Google Sheets (e.g., "November 2025")
  - Automatically copy header from "Main" tab when creating new month tabs
  - Fixed product column alignment in Google Sheets after adding refunds column

### Version 1.3.0 (2025-11-27)
- **Order Comparison Tool Improvements**:
  - Fixed timezone handling: Changed from America/New_York to UTC to match Complyt CSV timezone
  - Added country filtering for Complyt CSV: Filters by `shippingAddress.country == 'USA'` when "USA orders only" is enabled
  - Improved order ID normalization for better matching between Complyt and WooCommerce
  - Enhanced progress bar accuracy: Progress now reflects actual time distribution (WooCommerce fetching: 5-95%, CSV parsing: 5%, processing: 95-98%)
  - Added detailed logging for debugging order mismatches

## 🚀 Features

### Tools
- **Sales Tax Processing**: Upload and process CSV files for sales tax calculations
- **Order Comparison Tool**: Compare Complyt CSV data with WooCommerce orders and refunds, generating detailed CSV reports. Features UTC timezone matching, country/state filtering, and accurate progress tracking.
- **Inventory Data Management**: Aggregate inventory data from Zenventory and ShipBob APIs, export to CSV/ZIP and Google Sheets
- **Ulta Marketplace Exports**: Export Ulta Marketplace order data with date range selection, export to CSV and Google Sheets

### Scheduled Exports
- **Flexible Scheduling**: Create scheduled exports with multiple periods:
  - Minute-based (for testing)
  - Daily (with time selection)
  - Weekly (with day of week selection)
  - Monthly (with day of month selection)
- **Frequency Control**: Set frequency for all periods (e.g., every 5 minutes, every 3 days)
- **Export Options**: Choose export destinations:
  - Export to File (CSV/ZIP)
  - Export to Google Sheets
  - Or both
- **CRUD Interface**: Full management interface for scheduled exports:
  - Create new scheduled exports
  - View list of all scheduled exports
  - Edit existing scheduled exports
  - Enable/disable scheduled exports
  - Delete scheduled exports
- **Manual Exports**: Run exports on-demand with selective export options

### Integrations
- **WooCommerce Integration**: Connect with WooCommerce stores to fetch order data
- **Braintree Integration**: Process payment transactions through Braintree
- **AfterShip Integration**: Track shipments and delivery status
- **Ulta Marketplace API**: Fetch and export order data from Ulta Marketplace
- **Zenventory API**: Fetch inventory data from Zenventory KLB
- **ShipBob API**: Fetch inventory data from ShipBob fulfillment centers
- **Google Sheets Integration**: Export data directly to Google Sheets with OAuth 2.0 authentication

### Infrastructure
- **Background Job Processing**: Asynchronous job processing with Redis Queue (RQ)
- **User Authentication**: Secure JWT-based authentication system
- **Modern UI**: Built with Vue.js 3 and PrimeVue components
- **RESTful API**: FastAPI backend with automatic API documentation

## 🛠️ Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **PostgreSQL** - Relational database
- **Redis** - Caching and job queue
- **SQLAlchemy** - ORM for database operations
- **RQ (Redis Queue)** - Background job processing
- **JWT** - Authentication tokens

### Frontend
- **Vue.js 3** - Progressive JavaScript framework
- **PrimeVue** - UI component library
- **Vite** - Build tool and dev server
- **Vue Router** - Client-side routing

### Infrastructure
- **Docker** - Containerization
- **Docker Compose** - Multi-container orchestration
- **Nginx** - Reverse proxy and static file serving

## 📋 Prerequisites

- Docker and Docker Compose installed
- Git
- (For development) Node.js 20+ and Python 3.12+

## 🏃 Quick Start

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/ri5pekt/pfm-tools.git
   cd pfm-tools
   ```

2. **Create environment file**
   ```bash
   cp env .env
   # Edit .env with your configuration
   ```

3. **Start services**
   ```bash
   docker-compose up -d
   ```

4. **Create admin user**
   ```bash
   docker-compose exec backend python -m app.scripts.create_user --email admin@example.com --admin --password yourpassword
   ```

5. **Access the application**
   - Frontend: http://localhost:5173 (dev server) or http://localhost:8080 (Docker)
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

### Frontend Development (Optional)

If you prefer to run the frontend separately:

```bash
cd frontend
npm install
npm run dev
```

## 🏗️ Project Structure

```
pfm-tools/
├── backend/              # FastAPI backend application
│   ├── app/
│   │   ├── auth/        # Authentication module
│   │   ├── core/        # Core configuration and database
│   │   ├── features/    # Feature modules (sales_tax_processor)
│   │   ├── jobs/        # Job models and queues
│   │   └── scripts/     # Utility scripts
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/            # Vue.js frontend application
│   ├── src/
│   │   ├── api/         # API client functions
│   │   ├── components/  # Vue components
│   │   ├── views/       # Page views
│   │   └── store/       # State management
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml   # Development configuration
├── docker-compose.prod.yml  # Production configuration
└── README.md
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the root directory with the following variables:

```bash
# Core Configuration
APP_ENV=development
SECRET_KEY=your-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Database
DATABASE_URL=postgresql+psycopg2://pfmtools:pfmtools@db:5432/pfmtools
POSTGRES_PASSWORD=your-db-password

# Redis
REDIS_URL=redis://redis:6379/0
RQ_DEFAULT_QUEUE=pfmtools

# CORS
BACKEND_CORS_ORIGINS=["http://localhost:5173"]

# API Integrations
WOO_BASE_URL=https://your-store.com
WOO_CONSUMER_KEY=your-key
WOO_CONSUMER_SECRET=your-secret

BRAINTREE_MERCHANT_ID=your-merchant-id
BRAINTREE_PUBLIC_KEY=your-public-key
BRAINTREE_PRIVATE_KEY=your-private-key
BRAINTREE_ENVIRONMENT=sandbox  # or production

AFTERSHIP_USERNAME=your-username
AFTERSHIP_PASSWORD=your-password
AFTERSHIP_BASE_URL=https://api.us.afterpay.com

# Ulta Marketplace API
ULTA_API_KEY=your-ulta-api-key
ULTA_GOOGLE_SHEETS_SPREADSHEET_ID=your-ulta-spreadsheet-id
ULTA_GOOGLE_SHEETS_SHEET_NAME=Main

# Inventory Data APIs
ZENVENTORY_KLB_USERNAME=your-zenventory-username
ZENVENTORY_KLB_PASSWORD=your-zenventory-password
SHIPBOB_API_KEY=your-shipbob-api-key
INVENTORY_GOOGLE_SHEETS_SPREADSHEET_ID=your-inventory-spreadsheet-id

# Google Sheets OAuth Configuration
GOOGLE_SHEETS_OAUTH_CREDENTIALS_PATH=credentials/client_secret_google_sheets.json
GOOGLE_SHEETS_OAUTH_TOKEN_PATH=credentials/google_sheets_token.pickle

# Frontend Build
VITE_API_BASE_URL=http://localhost:8000/api
```

## 🚢 Production Deployment

For detailed production deployment instructions, see [README_PRODUCTION.md](README_PRODUCTION.md).

### Quick Production Setup

1. **Clone and configure**
   ```bash
   git clone https://github.com/ri5pekt/pfm-tools.git
   cd pfm-tools
   # Create .env file with production values
   ```

2. **Build and start**
   ```bash
   docker compose -f docker-compose.prod.yml build
   docker compose -f docker-compose.prod.yml up -d --scale worker=3
   ```

   **Note:** The scheduler service is required for scheduled exports to work. It starts automatically with the above command.

3. **Set up Nginx reverse proxy** (see production guide)

4. **Configure SSL** with Let's Encrypt

## 📚 API Documentation

Once the backend is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Authentication

Most endpoints require authentication. Include the JWT token in the Authorization header:

```
Authorization: Bearer <your-token>
```

### Example API Calls

```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "yourpassword"}'

# Health check
curl http://localhost:8000/api/health
```

## 👥 User Management

### Create Admin User

```bash
docker-compose exec backend python -m app.scripts.create_user \
  --email admin@example.com \
  --admin \
  --password yourpassword
```

### Create Regular User

```bash
docker-compose exec backend python -m app.scripts.create_user \
  --email user@example.com \
  --password userpassword
```

## 🔍 Troubleshooting

### Check Service Status

```bash
docker-compose ps
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f worker
```

### Run Diagnostic Script

```bash
./diagnose.sh
```

### Common Issues

**Backend not starting:**
- Check database connection in `.env`
- Verify Redis is running
- Check logs: `docker-compose logs backend`

**Frontend not loading:**
- Ensure backend is running on port 8000
- Check CORS settings in `.env`
- Verify `VITE_API_BASE_URL` is correct

**Jobs not processing:**
- Check worker containers are running
- Verify Redis connection
- Check worker logs: `docker-compose logs worker`

**Scheduled exports not triggering:**
- Verify scheduler service is running: `docker-compose ps scheduler`
- Check scheduler logs: `docker-compose logs scheduler`
- Ensure scheduled exports are enabled in the UI
- Verify Redis connection for scheduler

**Google Sheets export not working:**
- Check credentials files exist: `ls -la backend/credentials/`
- Verify credentials are mounted in containers (check docker-compose.yml volumes)
- Ensure OAuth token is not expired (it auto-refreshes if writable)
- Check worker logs for Google Sheets errors

## 🧪 Development

### Running Tests

```bash
# Backend tests (when implemented)
docker-compose exec backend pytest

# Frontend tests (when implemented)
cd frontend && npm test
```

### Code Formatting

```bash
# Backend (when configured)
docker-compose exec backend black .
docker-compose exec backend isort .

# Frontend
cd frontend && npm run format
```

## 📝 License

[Add your license here]

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📞 Support

For issues and questions, please open an issue on GitHub.

---

**Built with ❤️ using FastAPI, Vue.js, and Docker**

