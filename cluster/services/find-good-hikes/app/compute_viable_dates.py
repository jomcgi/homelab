"""
Compute viable dates for each walk location based on stored forecasts.
This should be run after forecasts are updated.
"""

import sqlite3
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from config import get_database_config, get_db_path

logger = logging.getLogger(__name__)

def compute_viable_dates_for_all_locations():
    """
    Compute viable dates for all walk locations and update the walks table.
    This reads from the forecasts database and updates the walks database.
    """
    try:
        db_config = get_database_config()
        walks_db_path = get_db_path(db_config.walks_db_path)
        forecasts_db_path = get_db_path(db_config.forecasts_db_path)
        
        if not Path(walks_db_path).exists():
            logger.error(f"Walks database not found: {walks_db_path}")
            return
            
        if not Path(forecasts_db_path).exists():
            logger.error(f"Forecasts database not found: {forecasts_db_path}")
            return
        
        with sqlite3.connect(walks_db_path, timeout=30.0) as walks_db, \
             sqlite3.connect(forecasts_db_path, timeout=30.0) as forecasts_db:
            
            # Get all walks
            walks_db.row_factory = sqlite3.Row
            walks_cursor = walks_db.cursor()
            walks_cursor.execute("SELECT uuid, name FROM walks")
            walks = walks_cursor.fetchall()
            
            logger.info(f"Computing viable dates for {len(walks)} locations...")
            
            # Set up forecasts database
            forecasts_db.row_factory = sqlite3.Row
            forecasts_cursor = forecasts_db.cursor()
            
            viable_dates_updated = 0
            
            for walk in walks:
                walk_uuid = walk['uuid']
                walk_name = walk['name']
                
                # Get distinct dates from forecasts for this location
                # Since we now filter at storage time, any forecast in the DB is viable
                forecasts_cursor.execute("""
                    SELECT DISTINCT DATE(time) as date
                    FROM forecasts 
                    WHERE location_id = ?
                      AND time > datetime('now')
                    ORDER BY date
                """, (walk_uuid,))
                
                rows = forecasts_cursor.fetchall()
                viable_dates = [row['date'] for row in rows]
                
                # Convert to JSON string for storage
                viable_dates_json = json.dumps(viable_dates) if viable_dates else None
                
                # Update the walks table
                walks_cursor.execute("""
                    UPDATE walks 
                    SET viable_dates = ?
                    WHERE uuid = ?
                """, (viable_dates_json, walk_uuid))
                
                viable_dates_updated += 1
                
                if viable_dates:
                    logger.debug(f"Updated {walk_name}: {len(viable_dates)} viable dates")
                else:
                    logger.debug(f"Updated {walk_name}: no viable dates")
            
            walks_db.commit()
            logger.info(f"Successfully updated viable dates for {viable_dates_updated} locations")
        
    except Exception as e:
        logger.error(f"Error computing viable dates: {e}")
        raise

if __name__ == "__main__":
    from logging_config import setup_logging
    setup_logging(level="INFO")
    compute_viable_dates_for_all_locations()
    print("Viable dates computation completed")