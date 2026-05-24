# backend/app/main.py

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.db import Base, engine
from app.jobs.models import Job, ScheduledExport, LowStockAlert  # Ensure models are registered
from app.auth.routes import router as auth_router
from app.features.sales_tax_processor.routes import router as sales_tax_router
from app.features.order_comparison.routes import router as order_comparison_router
from app.features.ulta_marketplace.routes import router as ulta_marketplace_router
from app.features.tiktok_marketplace.routes import router as tiktok_marketplace_router
from app.features.inventory_data.routes import router as inventory_data_router
try:
    from app.features.daily_orders_data.routes import router as daily_orders_data_router
except Exception as e:
    logging.error(f"Failed to import daily_orders_data router: {e}", exc_info=True)
    daily_orders_data_router = None

try:
    from app.features.daily_product_sales.routes import router as daily_product_sales_router
except Exception as e:
    logging.error(f"Failed to import daily_product_sales router: {e}", exc_info=True)
    daily_product_sales_router = None

try:
    from app.features.yt_influencers.routes import router as yt_influencers_router
except Exception as e:
    logging.error(f"Failed to import yt_influencers router: {e}", exc_info=True)
    yt_influencers_router = None

try:
    from app.features.one_time_vs_subscription.routes import router as one_time_vs_subscription_router
except Exception as e:
    logging.error(f"Failed to import one_time_vs_subscription router: {e}", exc_info=True)
    one_time_vs_subscription_router = None

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

# Add frequency column to scheduled_exports if it doesn't exist (migration)
try:
    from sqlalchemy import text, inspect
    from app.core.db import SessionLocal

    inspector = inspect(engine)
    if 'scheduled_exports' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('scheduled_exports')]
        if 'frequency' not in columns:
            logger = logging.getLogger(__name__)
            logger.info("Adding 'frequency' column to scheduled_exports table...")
            db = SessionLocal()
            try:
                db.execute(text("ALTER TABLE scheduled_exports ADD COLUMN frequency INTEGER DEFAULT 1 NOT NULL"))
                db.commit()
                logger.info("✓ Successfully added 'frequency' column")
            except Exception as e:
                logger.warning(f"Could not add frequency column (may already exist): {e}")
                db.rollback()
            finally:
                db.close()
except Exception as e:
    # Non-critical, just log it
    logging.getLogger(__name__).debug(f"Migration check skipped: {e}")

# Add low_stock_alerts columns if they don't exist (safe migration)
try:
    from sqlalchemy import text, inspect
    from app.core.db import SessionLocal

    inspector = inspect(engine)
    if "low_stock_alerts" in inspector.get_table_names():
        columns = [col["name"] for col in inspector.get_columns("low_stock_alerts")]
        logger = logging.getLogger(__name__)
        db = SessionLocal()
        try:
            migrations = [
                ("times", "ALTER TABLE low_stock_alerts ADD COLUMN times JSONB"),
                ("rq_job_ids", "ALTER TABLE low_stock_alerts ADD COLUMN rq_job_ids JSONB"),
                ("klb_threshold", "ALTER TABLE low_stock_alerts ADD COLUMN klb_threshold INTEGER"),
                ("shipbob_threshold", "ALTER TABLE low_stock_alerts ADD COLUMN shipbob_threshold INTEGER"),
            ]
            for column_name, sql in migrations:
                if column_name not in columns:
                    logger.info(f"Adding '{column_name}' column to low_stock_alerts table...")
                    db.execute(text(sql))
                    db.commit()
                    logger.info(f"Successfully added '{column_name}' column")

            db.execute(text("""
                UPDATE low_stock_alerts
                SET klb_threshold = threshold, shipbob_threshold = threshold
                WHERE (klb_threshold IS NULL OR shipbob_threshold IS NULL)
                  AND threshold IS NOT NULL
            """))
            db.commit()
        except Exception as e:
            logger.warning(f"Could not migrate low_stock_alerts table: {e}")
            db.rollback()
        finally:
            db.close()
except Exception as e:
    logging.getLogger(__name__).debug(f"Low stock alerts migration check skipped: {e}")

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

# Ulta Marketplace → available at /api/app/ulta-marketplace/* (prefix already defined in router)
app.include_router(ulta_marketplace_router)

# TikTok Marketplace → available at /api/app/tiktok-marketplace/* (prefix already defined in router)
app.include_router(tiktok_marketplace_router)

# Inventory Data → available at /api/app/inventory-data/* (prefix already defined in router)
app.include_router(inventory_data_router)

# Daily Orders Data → available at /api/app/daily-orders-data/* (prefix already defined in router)
if daily_orders_data_router:
    app.include_router(daily_orders_data_router)
else:
    logging.error("Daily Orders Data router is None - not including routes")

# Daily Product Sales → available at /api/app/daily-product-sales/* (prefix already defined in router)
if daily_product_sales_router:
    app.include_router(daily_product_sales_router)
else:
    logging.error("Daily Product Sales router is None - not including routes")

# YT Influencers → available at /api/app/yt-influencers/* (prefix already defined in router)
if yt_influencers_router:
    app.include_router(yt_influencers_router)
else:
    logging.error("YT Influencers router is None - not including routes")

# One-Time vs Subscription → available at /api/app/one-time-vs-subscription/* (prefix already defined in router)
if one_time_vs_subscription_router:
    app.include_router(one_time_vs_subscription_router)
else:
    logging.error("One-Time vs Subscription router is None - not including routes")

# Other modules later:
# app.include_router(taxes_router, prefix="/api/taxes")
# app.include_router(users_router, prefix="/api/users")
# app.include_router(reports_router, prefix="/api/reports")
