import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import httpx
import aiofiles


class GitHubClient:
    """Client for fetching markdown files from GitHub repositories."""
    
    def __init__(self, repo_url: str, token: Optional[str] = None, 
                 branch: str = "main", path_prefix: str = ""):
        self.repo_url = repo_url.rstrip("/")
        self.token = token
        self.branch = branch
        self.path_prefix = path_prefix.strip("/")
        
        # Parse owner and repo from URL or repo format
        if "github.com/" in repo_url:
            # Full URL format: https://github.com/owner/repo
            parts = repo_url.split("github.com/")[-1].split("/")
            self.owner = parts[0]
            self.repo = parts[1]
        elif "/" in repo_url and not repo_url.startswith(("http://", "https://")):
            # Short format: owner/repo
            parts = repo_url.split("/")
            self.owner = parts[0]
            self.repo = parts[1]
        else:
            raise ValueError(f"Invalid GitHub URL: {repo_url}. Use format 'owner/repo' or 'https://github.com/owner/repo'")
        
        # HTTP client with optional authentication
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        self.client = httpx.AsyncClient(headers=headers)
        
        # Use cache directory if it exists, otherwise current directory
        cache_dir = Path("/app/cache")
        if not cache_dir.exists():
            cache_dir = Path(".")
        
        self.cache_file = cache_dir / "raw_files_cache.json"
        self._files_cache: Dict[str, str] = {}  # path -> content
        self._last_commit_sha: Optional[str] = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def initialize(self) -> None:
        """Initialize the client and load cached files if available."""
        await self._load_cache()
        
        # Check if repository has been updated
        current_sha = await self._get_latest_commit_sha()
        if current_sha != self._last_commit_sha:
            print(f"Repository updated (SHA: {current_sha}), refreshing cache...")
            await self._refresh_files_cache()
            await self._save_cache()
    
    async def _get_latest_commit_sha(self) -> str:
        """Get the latest commit SHA for the specified branch."""
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/commits/{self.branch}"
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()["sha"]
    
    async def _get_file_tree(self) -> List[Dict]:
        """Get all markdown files in the repository."""
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/git/trees/{self.branch}?recursive=1"
        response = await self.client.get(url)
        response.raise_for_status()
        
        tree = response.json()["tree"]
        markdown_files = []
        
        for item in tree:
            if item["type"] == "blob" and item["path"].endswith(".md"):
                # Filter by path prefix if specified
                if not self.path_prefix or item["path"].startswith(self.path_prefix):
                    markdown_files.append(item)
        
        return markdown_files
    
    async def _fetch_file_content(self, file_path: str) -> str:
        """Fetch the content of a specific file."""
        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/contents/{file_path}?ref={self.branch}"
        response = await self.client.get(url)
        response.raise_for_status()
        
        file_data = response.json()
        if file_data["encoding"] == "base64":
            import base64
            return base64.b64decode(file_data["content"]).decode("utf-8")
        else:
            return file_data["content"]
    
    async def _refresh_files_cache(self) -> None:
        """Refresh the files cache by fetching all markdown files."""
        print("Refreshing files cache from GitHub...")
        markdown_files = await self._get_file_tree()
        
        # Fetch all files concurrently (but limit concurrency)
        semaphore = asyncio.Semaphore(5)  # Limit to 5 concurrent requests
        
        async def fetch_file(file_info):
            async with semaphore:
                try:
                    content = await self._fetch_file_content(file_info["path"])
                    return file_info["path"], content
                except Exception as e:
                    print(f"Error fetching {file_info['path']}: {e}")
                    return None, None
        
        tasks = [fetch_file(file_info) for file_info in markdown_files]
        results = await asyncio.gather(*tasks)
        
        # Update cache with successfully fetched files
        self._files_cache = {
            path: content for path, content in results 
            if path is not None and content is not None
        }
        
        # Update commit SHA
        self._last_commit_sha = await self._get_latest_commit_sha()
        
        print(f"Cached {len(self._files_cache)} files")
    
    async def _load_cache(self) -> None:
        """Load files cache from local file."""
        if not self.cache_file.exists():
            return
        
        try:
            async with aiofiles.open(self.cache_file, "r") as f:
                cache_data = json.loads(await f.read())
                
                self._last_commit_sha = cache_data.get("commit_sha")
                self._files_cache = cache_data.get("files", {})
                
                print(f"Loaded {len(self._files_cache)} files from cache")
        except Exception as e:
            print(f"Error loading cache: {e}")
            self._files_cache = {}
            self._last_commit_sha = None
    
    async def _save_cache(self) -> None:
        """Save files cache to local file."""
        try:
            cache_data = {
                "commit_sha": self._last_commit_sha,
                "files": self._files_cache
            }
            
            async with aiofiles.open(self.cache_file, "w") as f:
                await f.write(json.dumps(cache_data, indent=2))
        except Exception as e:
            print(f"Error saving cache: {e}")
    
    def get_all_file_paths(self) -> List[str]:
        """Get all cached file paths."""
        return list(self._files_cache.keys())
    
    def get_file_content(self, path: str) -> Optional[str]:
        """Get the raw content of a specific file."""
        return self._files_cache.get(path)
    
    def get_all_files(self) -> List[Tuple[str, str]]:
        """Get all files as (path, content) tuples."""
        return [(path, content) for path, content in self._files_cache.items()]