#!/usr/bin/env python3
import requests
import json
from datetime import datetime, timedelta
import logging
import argparse
import subprocess
import os

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Default Configuration (can be overridden by env vars or args)
DEFAULT_REGISTRY_URL = "http://registry.localhost"
DEFAULT_DELETE_OLDER_THAN_DAYS = 3
DEFAULT_DRY_RUN = True

def get_catalog(registry_url):
    """Get list of all repositories in the registry"""
    response = requests.get(f"{registry_url}/v2/_catalog")
    response.raise_for_status()
    return response.json().get("repositories", [])

def get_tags(registry_url, repository):
    """Get all tags for a repository"""
    response = requests.get(f"{registry_url}/v2/{repository}/tags/list")
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json().get("tags", [])

def get_manifest_digest(registry_url, repository, tag):
    """Get the digest for a specific tag"""
    headers = {"Accept": "application/vnd.docker.distribution.manifest.v2+json"}
    response = requests.head(
        f"{registry_url}/v2/{repository}/manifests/{tag}",
        headers=headers
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    
    # Try different header case variations
    digest = response.headers.get("Docker-Content-Digest") or \
             response.headers.get("docker-content-digest") or \
             response.headers.get("Docker-content-digest")
    
    if not digest:
        logger.warning(f"No digest found for {repository}:{tag}. Headers: {dict(response.headers)}")
        
    return digest

def get_manifest(registry_url, repository, tag):
    """Get the manifest for a specific tag to extract creation date"""
    headers = {"Accept": "application/vnd.docker.distribution.manifest.v2+json"}
    response = requests.get(
        f"{registry_url}/v2/{repository}/manifests/{tag}",
        headers=headers
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()

def is_older_than_days(registry_url, repository, tag, days):
    """Check if image is older than specified days"""
    manifest = get_manifest(registry_url, repository, tag)
    if not manifest:
        return False
    
    # Try to extract creation date from image config
    if 'history' in manifest and manifest['history']:
        for item in manifest['history']:
            if isinstance(item, dict) and 'v1Compatibility' in item:
                v1_data = json.loads(item['v1Compatibility'])
                if 'created' in v1_data:
                    created_str = v1_data['created']
                    created_date = datetime.fromisoformat(created_str.rstrip('Z'))
                    age = datetime.now() - created_date
                    return age > timedelta(days=days)
    
    # If we can't determine age, assume it's not old
    return False

def delete_manifest_by_digest(registry_url, repository, digest, dry_run):
    """
    Delete a manifest by digest using the Registry API directly
    """
    if dry_run:
        logger.info(f"DRY RUN: Would delete manifest {repository}@{digest}")
        return True
    
    try:
        response = requests.delete(f"{registry_url}/v2/{repository}/manifests/{digest}")
        if response.status_code == 202:
            logger.info(f"Successfully deleted manifest {repository}@{digest}")
            return True
        else:
            logger.error(f"Failed to delete manifest {repository}@{digest}: HTTP {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error deleting manifest {repository}@{digest}: {e}")
        return False

def delete_tag(registry_url, repository, tag, dry_run):
    """
    Delete a tag by removing the manifest it points to
    """
    if dry_run:
        logger.info(f"DRY RUN: Would remove tag {repository}:{tag}")
        return True
    
    # First, get the digest for this tag
    digest = get_manifest_digest(registry_url, repository, tag)
    if not digest:
        logger.error(f"Could not find digest for {repository}:{tag}")
        return False
        
    # Delete the manifest using the digest
    return delete_manifest_by_digest(registry_url, repository, digest, dry_run)

def main():
    # Read from environment variables with defaults
    registry_url = os.environ.get("REGISTRY_URL", DEFAULT_REGISTRY_URL)
    delete_older_than_days = int(os.environ.get("DELETE_OLDER_THAN_DAYS", DEFAULT_DELETE_OLDER_THAN_DAYS))
    dry_run = os.environ.get("DRY_RUN", str(DEFAULT_DRY_RUN)).lower() in ["true", "1", "yes"]
    
    # Set up command-line arguments (these will override environment variables)
    parser = argparse.ArgumentParser(description='Clean up old Docker images in registry')
    parser.add_argument('--registry-url', type=str, default=registry_url,
                       help=f'Registry URL (default: {registry_url})')
    parser.add_argument('--days', type=int, default=delete_older_than_days,
                        help=f'Delete images older than this many days (default: {delete_older_than_days})')
    parser.add_argument('--no-dry-run', action='store_true',
                        help='Actually perform deletions (default: dry run)')
    args = parser.parse_args()
    
    # Command-line args override environment variables
    registry_url = args.registry_url
    delete_older_than_days = args.days
    
    dry_run = not args.no_dry_run
    
    cutoff_date = datetime.now() - timedelta(days=delete_older_than_days)
    logger.info(f"Starting cleanup of images older than {cutoff_date.isoformat()}")
    logger.info(f"Registry URL: {registry_url}")
    logger.info(f"Dry run: {dry_run}")
    
    repositories = get_catalog(registry_url)
    logger.info(f"Found {len(repositories)} repositories")
    
    tags_removed = 0
    
    for repository in repositories:
        tags = get_tags(registry_url, repository)
        logger.info(f"Repository {repository} has {len(tags)} tags")
        
        # Check if 'latest' tag exists
        has_latest = 'latest' in tags
        
        for tag in tags:
            # Skip the latest tag if it exists
            if tag == 'latest' and has_latest:
                continue
                
            should_delete = False
            
            # Check age condition
            if is_older_than_days(registry_url, repository, tag, delete_older_than_days):
                logger.info(f"Image {repository}:{tag} is older than {delete_older_than_days} days")
                should_delete = True
            elif not has_latest:
                logger.info(f"Image {repository}:{tag} has no 'latest' tag")
                should_delete = True
            
            if should_delete:
                if delete_tag(registry_url, repository, tag, dry_run):
                    tags_removed += 1
    
    logger.info(f"Total tags removed: {tags_removed}")

if __name__ == "__main__":
    main()