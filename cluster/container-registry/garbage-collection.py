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

# Configuration
REGISTRY_URL = "http://registry.localhost"
DELETE_OLDER_THAN_DAYS = 3
DRY_RUN = True  # Set to False to actually remove tags

def get_catalog():
    """Get list of all repositories in the registry"""
    response = requests.get(f"{REGISTRY_URL}/v2/_catalog")
    response.raise_for_status()
    return response.json().get("repositories", [])

def get_tags(repository):
    """Get all tags for a repository"""
    response = requests.get(f"{REGISTRY_URL}/v2/{repository}/tags/list")
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json().get("tags", [])

def get_manifest_digest(repository, tag):
    """Get the digest for a specific tag"""
    headers = {"Accept": "application/vnd.docker.distribution.manifest.v2+json"}
    response = requests.head(
        f"{REGISTRY_URL}/v2/{repository}/manifests/{tag}",
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

def get_manifest(repository, tag):
    """Get the manifest for a specific tag to extract creation date"""
    headers = {"Accept": "application/vnd.docker.distribution.manifest.v2+json"}
    response = requests.get(
        f"{REGISTRY_URL}/v2/{repository}/manifests/{tag}",
        headers=headers
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()

def is_older_than_days(repository, tag, days):
    """Check if image is older than specified days"""
    manifest = get_manifest(repository, tag)
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

def delete_tag(repository, tag):
    """
    'Delete' a tag by removing its reference.
    Since registry doesn't have deletion enabled, we can only untag the image.
    """
    if DRY_RUN:
        logger.info(f"DRY RUN: Would remove tag {repository}:{tag}")
        return True
    
    # To untag in Docker Registry v2, we need to use Docker CLI
    # This is a workaround since the registry API doesn't support direct untagging
    # We're using the docker command line to remove the tag
    try:
        # Pull the image (to ensure we have it locally)
        subprocess.run(["docker", "pull", f"{repository}:{tag}"], check=False)
        
        # Remove the tag (untag the image)
        subprocess.run(["docker", "rmi", f"{repository}:{tag}"], check=True)
        
        # Push the updated repository to the registry (now without the tag)
        subprocess.run(["docker", "push", repository], check=True)
        
        logger.info(f"Successfully removed tag {repository}:{tag}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to remove tag {repository}:{tag}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Clean up old Docker images in registry')
    parser.add_argument('--days', type=int, default=DELETE_OLDER_THAN_DAYS,
                        help=f'Delete images older than this many days (default: {DELETE_OLDER_THAN_DAYS})')
    parser.add_argument('--no-dry-run', action='store_true',
                        help='Actually perform deletions (default: dry run)')
    args = parser.parse_args()
    
    global DRY_RUN
    DRY_RUN = not args.no_dry_run
    
    cutoff_date = datetime.now() - timedelta(days=args.days)
    logger.info(f"Starting cleanup of images older than {cutoff_date.isoformat()}")
    logger.info(f"Dry run: {DRY_RUN}")
    
    repositories = get_catalog()
    logger.info(f"Found {len(repositories)} repositories")
    
    tags_removed = 0
    
    for repository in repositories:
        tags = get_tags(repository)
        logger.info(f"Repository {repository} has {len(tags)} tags")
        
        # Check if 'latest' tag exists
        has_latest = 'latest' in tags
        
        for tag in tags:
            # Skip the latest tag if it exists
            if tag == 'latest' and has_latest:
                continue
                
            should_delete = False
            
            # Check age condition
            if is_older_than_days(repository, tag, args.days):
                logger.info(f"Image {repository}:{tag} is older than {args.days} days")
                should_delete = True
            elif not has_latest:
                logger.info(f"Image {repository}:{tag} has no 'latest' tag")
                should_delete = True
            
            if should_delete:
                if delete_tag(repository, tag):
                    tags_removed += 1
    
    logger.info(f"Total tags removed: {tags_removed}")

if __name__ == "__main__":
    main()