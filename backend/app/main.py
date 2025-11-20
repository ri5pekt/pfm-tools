# backend/app/main.py

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.db import Base, engine
from app.auth.routes import router as auth_router
from app.features.sales_tax_processor.routes import router as sales_tax_router
from app.features.order_comparison.routes import router as order_comparison_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Load settings
settings = get_settings()

# =====================================================
# Create tables (dev only)
# =====================================================
Base.metadata.create_all(bind=engine)

# =====================================================
# FastAPI app
# =====================================================
app = FastAPI(title="PFM Tools API")


# =====================================================
# CORS configuration
# =====================================================

# Fallback dev origins
default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# If settings.backend_cors_origins is empty, use defaults
cors_origins = (
    [str(o) for o in settings.backend_cors_origins]
    if settings.backend_cors_origins and len(settings.backend_cors_origins) > 0
    else default_origins
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# =====================================================
# Health endpoint
# =====================================================
@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# =====================================================
# Routers
# =====================================================
# Auth → available at /api/auth/* (prefix already defined in router)
app.include_router(auth_router)

# Sales Tax Processor → available at /api/app/sales-tax-processor/* (prefix already defined in router)
app.include_router(sales_tax_router)

# Order Comparison → available at /api/app/order-comparison/* (prefix already defined in router)
app.include_router(order_comparison_router)

# Other modules later:
# app.include_router(taxes_router, prefix="/api/taxes")
# app.include_router(users_router, prefix="/api/users")
# app.include_router(reports_router, prefix="/api/reports")
