#!/usr/bin/env python3
"""Upload generated data to Cloudflare R2."""

import os
import sys
import json
import logging
from pathlib import Path
import mimetypes

import boto3
from botocore.exceptions import ClientError

from config import (
    DATA_DIR, R2_BUCKET_NAME, R2_ENDPOINT,
    R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_r2_client():
    """Create S3 client configured for Cloudflare R2."""
    if not all([R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY]):
        raise ValueError("R2 credentials not configured. Set CLOUDFLARE_S3_ENDPOINT, CLOUDFLARE_S3_ACCESS_KEY_ID, and CLOUDFLARE_S3_ACCESS_KEY_SECRET environment variables.")
    
    return boto3.client(
        service_name='s3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name='auto'
    )


def upload_file(s3_client, local_path: Path, s3_key: str):
    """Upload a single file to R2."""
    try:
        # Determine content type
        content_type, _ = mimetypes.guess_type(str(local_path))
        if content_type is None:
            content_type = 'application/json' if local_path.suffix == '.json' else 'application/octet-stream'
        
        # Upload with metadata
        with open(local_path, 'rb') as f:
            s3_client.put_object(
                Bucket=R2_BUCKET_NAME,
                Key=s3_key,
                Body=f,
                ContentType=content_type,
                CacheControl='public, max-age=3600',  # Cache for 1 hour
            )
        
        logger.info(f"Uploaded {s3_key}")
        return True
        
    except ClientError as e:
        logger.error(f"Failed to upload {s3_key}: {e}")
        return False


def sync_to_r2():
    """Sync all generated data to R2."""
    logger.info(f"Starting sync to R2 bucket: {R2_BUCKET_NAME}")
    
    # Create S3 client
    try:
        s3_client = create_r2_client()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return False
    
    # Upload all files
    upload_count = 0
    error_count = 0
    
    # Upload index.json
    index_path = DATA_DIR / "index.json"
    if index_path.exists():
        if upload_file(s3_client, index_path, "index.json"):
            upload_count += 1
        else:
            error_count += 1
    
    # Upload all walk files
    walks_dir = DATA_DIR / "walks"
    if walks_dir.exists():
        for walk_file in walks_dir.glob("*.json"):
            s3_key = f"walks/{walk_file.name}"
            if upload_file(s3_client, walk_file, s3_key):
                upload_count += 1
            else:
                error_count += 1
    
    # Upload metadata file with last update time
    metadata = {
        "last_updated": index_path.stat().st_mtime if index_path.exists() else 0,
        "total_files": upload_count,
        "bucket": R2_BUCKET_NAME
    }
    metadata_path = DATA_DIR / "metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f)
    
    if upload_file(s3_client, metadata_path, "metadata.json"):
        upload_count += 1
    else:
        error_count += 1
    
    logger.info(f"Sync complete: {upload_count} uploaded, {error_count} errors")
    return error_count == 0


def main():
    """Main entry point."""
    if not sync_to_r2():
        logger.error("R2 sync failed")
        sys.exit(1)
    else:
        logger.info("R2 sync completed successfully")


if __name__ == "__main__":
    main()