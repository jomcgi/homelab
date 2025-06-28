#!/usr/bin/env python3
"""Clean up unused objects in R2 bucket for find-good-hikes."""

import boto3
import os
import sys
from botocore.config import Config
from datetime import datetime
import json


def setup_r2_client():
    """Set up R2 client using environment variables."""
    try:
        client = boto3.client(
            's3',
            endpoint_url=os.environ['CLOUDFLARE_S3_ENDPOINT'],
            aws_access_key_id=os.environ['CLOUDFLARE_S3_ACCESS_KEY_ID'],
            aws_secret_access_key=os.environ['CLOUDFLARE_S3_ACCESS_KEY_SECRET'],
            config=Config(
                signature_version='s3v4',
                retries={'max_attempts': 3, 'mode': 'standard'}
            ),
            region_name='auto'
        )
        return client
    except KeyError as e:
        print(f"Missing environment variable: {e}")
        print("Required variables: CLOUDFLARE_S3_ENDPOINT, CLOUDFLARE_S3_ACCESS_KEY_ID, CLOUDFLARE_S3_ACCESS_KEY_SECRET")
        sys.exit(1)


def list_all_objects(client, bucket_name):
    """List all objects in the bucket."""
    objects = []
    try:
        paginator = client.get_paginator('list_objects_v2')
        
        for page in paginator.paginate(Bucket=bucket_name):
            if 'Contents' in page:
                objects.extend(page['Contents'])
    except client.exceptions.NoSuchBucket:
        print(f"❌ Bucket '{bucket_name}' does not exist.")
        sys.exit(1)
    except Exception as e:
        # Try alternative list method
        print(f"⚠️  ListObjectsV2 failed ({e}), trying legacy ListObjects...")
        try:
            response = client.list_objects(Bucket=bucket_name)
            if 'Contents' in response:
                objects.extend(response['Contents'])
        except Exception as e2:
            print(f"❌ Both list methods failed: {e2}")
            sys.exit(1)
    
    return objects


def format_size(size_bytes):
    """Format file size in human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def main():
    """Main cleanup function."""
    bucket_name = os.environ.get('R2_BUCKET_NAME', 'jomcgi-hikes')
    
    print(f"🧹 R2 Bucket Cleanup Tool")
    print(f"Bucket: {bucket_name}")
    print("Mode: Auto-confirm (CI)")
    print("=" * 50)
    
    # Set up client
    client = setup_r2_client()
    
    # Test bucket access first
    print("🔗 Testing bucket access...")
    try:
        response = client.head_bucket(Bucket=bucket_name)
        print(f"✅ Successfully connected to bucket '{bucket_name}'")
    except Exception as e:
        print(f"❌ Failed to access bucket '{bucket_name}': {e}")
        sys.exit(1)
    
    # List all objects
    print("📋 Listing all objects...")
    objects = list_all_objects(client, bucket_name)
    
    if not objects:
        print("✅ Bucket is already empty!")
        return
    
    print(f"Found {len(objects)} objects:")
    print()
    
    # Group objects by type
    current_files = []
    old_files = []
    other_files = []
    
    # Files we want to keep
    keep_files = {
        'bundle.json',           # New format
        'bundle.json.br'         # Old format (temporarily)
    }
    
    total_size = 0
    for obj in objects:
        key = obj['Key']
        size = obj['Size']
        modified = obj['LastModified']
        total_size += size
        
        if key in keep_files:
            current_files.append((key, size, modified))
        elif key.startswith('bundle') or key.endswith('.json') or key.endswith('.br'):
            old_files.append((key, size, modified))
        else:
            other_files.append((key, size, modified))
    
    # Display summary
    print(f"📊 SUMMARY:")
    print(f"  Total objects: {len(objects)}")
    print(f"  Total size: {format_size(total_size)}")
    print()
    
    if current_files:
        print(f"✅ CURRENT FILES ({len(current_files)}):")
        for key, size, modified in current_files:
            print(f"  📄 {key} ({format_size(size)}) - {modified.strftime('%Y-%m-%d %H:%M')}")
        print()
    
    if old_files:
        print(f"🗑️  OLD BUNDLE FILES ({len(old_files)}):")
        old_size = sum(size for _, size, _ in old_files)
        for key, size, modified in old_files[:10]:  # Show first 10
            print(f"  📄 {key} ({format_size(size)}) - {modified.strftime('%Y-%m-%d %H:%M')}")
        if len(old_files) > 10:
            print(f"  ... and {len(old_files) - 10} more files")
        print(f"  💾 Total size to delete: {format_size(old_size)}")
        print()
    
    if other_files:
        print(f"❓ OTHER FILES ({len(other_files)}):")
        other_size = sum(size for _, size, _ in other_files)
        for key, size, modified in other_files[:5]:  # Show first 5
            print(f"  📄 {key} ({format_size(size)}) - {modified.strftime('%Y-%m-%d %H:%M')}")
        if len(other_files) > 5:
            print(f"  ... and {len(other_files) - 5} more files")
        print(f"  💾 Total size: {format_size(other_size)}")
        print()
    
    # Ask for confirmation
    files_to_delete = old_files + other_files
    if not files_to_delete:
        print("✅ No files to delete!")
        return
    
    print(f"⚠️  READY TO DELETE {len(files_to_delete)} files")
    print("Files to keep:")
    for key, _, _ in current_files:
        print(f"  ✅ {key}")
    print()
    
    print("🤖 Auto-confirming deletion in CI mode...")
    
    # Delete files
    print(f"🗑️  Deleting {len(files_to_delete)} files...")
    
    # Delete in batches of 1000 (AWS limit)
    batch_size = 1000
    deleted_count = 0
    
    for i in range(0, len(files_to_delete), batch_size):
        batch = files_to_delete[i:i + batch_size]
        
        # Prepare delete request
        delete_objects = {
            'Objects': [{'Key': key} for key, _, _ in batch],
            'Quiet': True
        }
        
        try:
            response = client.delete_objects(
                Bucket=bucket_name,
                Delete=delete_objects
            )
            
            deleted_count += len(batch)
            print(f"  ✅ Deleted batch {i//batch_size + 1}: {deleted_count}/{len(files_to_delete)} files")
            
            if 'Errors' in response and response['Errors']:
                print(f"  ⚠️  Errors in batch: {len(response['Errors'])}")
                for error in response['Errors'][:3]:  # Show first 3 errors
                    print(f"    - {error['Key']}: {error['Code']} - {error['Message']}")
                    
        except Exception as e:
            print(f"  ❌ Error deleting batch: {e}")
    
    print()
    print(f"✅ Cleanup complete!")
    print(f"   Deleted: {deleted_count} files")
    print(f"   Kept: {len(current_files)} files")


if __name__ == '__main__':
    main()