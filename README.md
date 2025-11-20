# PFM Tools

**Version:** 1.1.0

A modern web application for processing sales tax data with integration to WooCommerce, Braintree, and AfterShip APIs.

## 🚀 Features

### Tools
- **Sales Tax Processing**: Upload and process CSV files for sales tax calculations
- **Order Comparison Tool**: Compare Complyt CSV data with WooCommerce orders and refunds, generating detailed PDF reports
- More tools coming soon...

### Scheduled Tasks
- **Automated Workflows**: Replace Zapier workflows with native scheduled tasks
- **Daily Stats Export**: Pull daily statistics and export to Google Sheets
- **Task Management**: Each task includes:
  - Report logs page with execution history
  - Manual run button for on-demand execution
  - Schedule configuration (cron-based)
  - Status monitoring and notifications

### Integrations
- **WooCommerce Integration**: Connect with WooCommerce stores to fetch order data
- **Braintree Integration**: Process payment transactions through Braintree
- **AfterShip Integration**: Track shipments and delivery status
- **Google Sheets Integration**: Export data to Google Sheets (planned)

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
   docker compose -f docker-compose.prod.yml up -d --scale worker=2
   ```

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

