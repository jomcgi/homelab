"""
Database index management for optimizing query performance.
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)

def create_walks_indexes(db_path: str):
    """Create indexes for the walks database to optimize spatial queries."""
    try:
        with sqlite3.connect(db_path, timeout=30.0) as conn:
            cursor = conn.cursor()
            
            # Index for spatial queries (latitude, longitude lookups)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_walks_location 
                ON walks (latitude, longitude)
            """)
            
            # Index for UUID lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_walks_uuid 
                ON walks (uuid)
            """)
            
            conn.commit()
            logger.info("Created indexes for walks database")
            
    except sqlite3.Error as e:
        logger.error(f"Error creating walks indexes: {e}")
        raise

def create_forecasts_indexes(db_path: str):
    """Create indexes for the forecasts database to optimize weather queries."""
    try:
        with sqlite3.connect(db_path, timeout=30.0) as conn:
            cursor = conn.cursor()
            
            # Most important: location_id index for joining with walks
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_forecasts_location_id 
                ON forecasts (location_id)
            """)
            
            # Time-based queries for viable dates
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_forecasts_time 
                ON forecasts (time)
            """)
            
            # Composite index for location + time queries (most common pattern)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_forecasts_location_time 
                ON forecasts (location_id, time)
            """)
            
            # Index for UUID lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_forecasts_uuid 
                ON forecasts (uuid)
            """)
            
            conn.commit()
            logger.info("Created indexes for forecasts database")
            
    except sqlite3.Error as e:
        logger.error(f"Error creating forecasts indexes: {e}")
        raise

def create_all_indexes(walks_db_path: str, forecasts_db_path: str):
    """Create all necessary indexes for both databases."""
    logger.info("Creating database indexes for performance optimization...")
    create_walks_indexes(walks_db_path)
    create_forecasts_indexes(forecasts_db_path)
    logger.info("All database indexes created successfully")