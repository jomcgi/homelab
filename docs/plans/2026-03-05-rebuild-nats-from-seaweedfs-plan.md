# Rebuild NATS Trip Data from SeaweedFS — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `rebuild` command to `scripts/publish-trip-images/main.py` that recovers trip metadata from SeaweedFS images and republishes to NATS with elevation data.

**Architecture:** List S3 bucket objects, download images in batches (80 at a time, ~440MB peak disk), extract EXIF for GPS/timestamp/optics, fetch elevation from NRCan API, populate `publish_queue.db`, and publish to NATS. Also fix the stream `max_age` to prevent data loss.

**Tech Stack:** Python, boto3 (S3), Pillow (EXIF), nats.py (JetStream), aiohttp (NRCan elevation API), typer (CLI), Rich (progress bars), SQLite (queue DB + caches)

---

### Task 1: Add `//scripts/elevation` dep to BUILD

**Files:**
- Modify: `scripts/publish-trip-images/BUILD` — add `//scripts/elevation` and `@pip//aiohttp` to both `py_venv_binary` and `py_library` targets

**Step 1: Update BUILD file**

Add `"//scripts/elevation"` and `"@pip//aiohttp"` to the `deps` lists for the `main` target (py_venv_binary, line 7-18) and the `publish-trip-images` target (py_library, line 5-19). The `elevation` library needs `aiohttp` as a transitive dep.

In `py_venv_binary` named `"main"` (line 7), add to deps:
```python
        "//scripts/elevation",
        "@pip//aiohttp",
```

In `py_library` named `"publish-trip-images"` (line 5), add to deps:
```python
        "//scripts/elevation",
        "@pip//aiohttp",
```

**Step 2: Verify BUILD parses**

Run: `cd /tmp/claude-worktrees/rebuild-nats && bazel query //scripts/publish-trip-images:main --output=build 2>&1 | head -20`
Expected: Shows the target with the new deps listed.

**Step 3: Commit**

```bash
git add scripts/publish-trip-images/BUILD
git commit -m "build(publish-trip-images): add elevation dependency for rebuild command"
```

---

### Task 2: Add `list_s3_keys` helper function

**Files:**
- Modify: `scripts/publish-trip-images/main.py` — add function after `ensure_bucket()` (after line 488)

**Step 1: Write `list_s3_keys` function**

Add this function after `ensure_bucket()` at line 488:

```python
def list_s3_keys(s3_client, bucket: str, prefix: str = "") -> list[str]:
    """List all object keys in an S3 bucket (paginated).

    Only returns keys with image extensions (.jpg, .jpeg, .png, .heic, .heif).
    """
    image_extensions = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
    keys = []
    continuation_token = None

    while True:
        kwargs = {"Bucket": bucket, "MaxKeys": 1000}
        if prefix:
            kwargs["Prefix"] = prefix
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token

        response = s3_client.list_objects_v2(**kwargs)

        for obj in response.get("Contents", []):
            key = obj["Key"]
            ext = Path(key).suffix.lower()
            if ext in image_extensions:
                keys.append(key)

        if not response.get("IsTruncated"):
            break
        continuation_token = response["NextContinuationToken"]

    return keys
```

**Step 2: Commit**

```bash
git add scripts/publish-trip-images/main.py
git commit -m "feat(publish-trip-images): add list_s3_keys helper for S3 bucket listing"
```

---

### Task 3: Add `_rebuild_batch` helper function

**Files:**
- Modify: `scripts/publish-trip-images/main.py` — add function after `list_s3_keys`

**Step 1: Write the batch processing helper**

This function downloads a batch of images from S3, extracts EXIF, adds to the queue DB, and cleans up. Add it after `list_s3_keys`:

```python
def _rebuild_batch(
    s3_client,
    bucket: str,
    keys: list[str],
    queue: UploadQueue,
    optics_cache: OpticsCache,
    tmp_dir: Path,
    source: str,
    concurrency: int,
) -> list[dict]:
    """Download a batch of images from S3, extract EXIF, add to queue.

    Returns list of point dicts (with lat/lng/timestamp/optics) for later
    elevation lookup and NATS publishing. Cleans up downloaded files after.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    points = []

    def download_and_extract(key: str) -> tuple[str, float | None, float | None, str | None, OpticsData | None]:
        """Download one image and extract EXIF. Runs in thread pool."""
        # Check optics cache first
        found, cached_optics = optics_cache.get(key)

        local_path = tmp_dir / key
        try:
            s3_client.download_file(bucket, key, str(local_path))
            lat, lng, timestamp, optics = extract_exif(local_path)

            # Cache optics result
            if not found:
                optics_cache.put(key, optics)
            elif cached_optics:
                # Use cached optics if we had them (extract_exif may return same)
                optics = cached_optics

            return key, lat, lng, timestamp, optics
        except Exception as e:
            print(f"  Warning: Failed to process {key}: {e}")
            return key, None, None, None, None

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(download_and_extract, key): key for key in keys}

        for future in as_completed(futures):
            key, lat, lng, timestamp, optics = future.result()

            # Skip images without GPS
            if lat is None or lng is None:
                continue

            # Add to queue DB (source_path is S3 key since local path is gone)
            record_id = queue.add(
                source_path=Path(key),
                dest_key=key,
                lat=lat,
                lng=lng,
                timestamp=timestamp,
                tags=None,
                optics=optics,
            )

            # Mark as completed immediately (image already in S3)
            if record_id:
                queue.mark_completed(record_id)

            # Collect point for elevation + NATS publishing
            point = {
                "key": key,
                "lat": lat,
                "lng": lng,
                "timestamp": timestamp,
                "optics": optics,
            }
            points.append(point)

    # Clean up downloaded files
    import shutil
    shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    return points
```

**Step 2: Commit**

```bash
git add scripts/publish-trip-images/main.py
git commit -m "feat(publish-trip-images): add _rebuild_batch helper for batched S3 processing"
```

---

### Task 4: Add `rebuild` typer command

**Files:**
- Modify: `scripts/publish-trip-images/main.py` — add import for `ElevationClient` at top, add `rebuild` command after `backfill_optics` (after line 1340)

**Step 1: Add elevation import**

At the top of the file, after the existing imports (after line 37, near the other imports), add:

```python
from scripts.elevation import ElevationClient
```

**Step 2: Write the rebuild command**

Add the `rebuild` command after the `backfill_optics` command (before `if __name__ == "__main__":`):

```python
@app.command()
def rebuild(
    bucket: Annotated[
        str, typer.Option("--bucket", "-b", help="S3 bucket name")
    ] = DEFAULT_BUCKET,
    batch_size: Annotated[
        int, typer.Option("--batch-size", help="Images per download batch")
    ] = 80,
    concurrency: Annotated[
        int, typer.Option("--concurrency", "-c", help="Parallel downloads per batch")
    ] = 10,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Extract and report only, don't publish"),
    ] = False,
    source: Annotated[
        str,
        typer.Option("--source", "-s", help="Image source tag"),
    ] = "gopro",
    db_path: Annotated[
        Path, typer.Option("--db", help="Path to upload queue database")
    ] = DB_PATH,
    fix_retention: Annotated[
        bool,
        typer.Option("--fix-retention/--no-fix-retention", help="Fix NATS stream max_age to unlimited"),
    ] = True,
) -> None:
    """Rebuild trip data from SeaweedFS when NATS stream data has been lost.

    Lists all images in the S3 bucket, downloads in batches to extract EXIF
    metadata (GPS, timestamps, camera settings), fetches elevation from NRCan,
    populates the local queue DB, and republishes all points to NATS.

    Disk usage is capped by processing images in batches (default 80 images
    ~440MB per batch). Temp files are cleaned between batches.

    Example:
        # Preview what would be recovered (dry run)
        publish-trip-images rebuild --dry-run

        # Full rebuild with elevation
        publish-trip-images rebuild

        # Custom batch size for lower disk usage
        publish-trip-images rebuild --batch-size 40
    """
    asyncio.run(
        _run_rebuild(
            bucket=bucket,
            batch_size=batch_size,
            concurrency=concurrency,
            dry_run=dry_run,
            source=source,
            db_path=db_path,
            fix_retention=fix_retention,
        )
    )
```

**Step 3: Write the `_run_rebuild` async function**

Add this above the `rebuild` command:

```python
async def _run_rebuild(
    bucket: str,
    batch_size: int,
    concurrency: int,
    dry_run: bool,
    source: str,
    db_path: Path,
    fix_retention: bool,
) -> None:
    """Main rebuild logic."""
    import shutil
    import tempfile

    queue = UploadQueue(db_path)
    optics_cache = OpticsCache(OPTICS_CACHE_PATH)
    s3_client = get_s3_client()

    # Step 1: Connect to NATS
    print("Connecting to NATS...")
    nc, js = await get_jetstream()

    try:
        # Step 2: Fix stream retention
        if fix_retention and not dry_run:
            try:
                stream_info = await js.stream_info("trips")
                config = stream_info.config
                if config.max_age and config.max_age > 0:
                    config.max_age = 0  # unlimited
                    await js.update_stream(config)
                    print("Fixed NATS stream max_age: removed 30d TTL (now unlimited)")
                else:
                    print("NATS stream max_age already unlimited")
            except Exception as e:
                print(f"Warning: Could not update stream retention: {e}")

        # Step 3: List all S3 keys
        print(f"Listing objects in s3://{bucket}...")
        all_keys = list_s3_keys(s3_client, bucket)
        print(f"Found {len(all_keys)} images in S3")

        if not all_keys:
            return

        # Step 4: Process in batches
        tmp_dir = Path(tempfile.mkdtemp(prefix="rebuild-"))
        all_points = []

        try:
            num_batches = (len(all_keys) + batch_size - 1) // batch_size

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
            ) as progress:
                task = progress.add_task(
                    f"Processing batches (0/{num_batches})...",
                    total=len(all_keys),
                )

                for batch_idx in range(0, len(all_keys), batch_size):
                    batch_keys = all_keys[batch_idx : batch_idx + batch_size]
                    batch_num = batch_idx // batch_size + 1

                    progress.update(
                        task,
                        description=f"Batch {batch_num}/{num_batches} ({len(batch_keys)} images)...",
                    )

                    batch_points = _rebuild_batch(
                        s3_client=s3_client,
                        bucket=bucket,
                        keys=batch_keys,
                        queue=queue,
                        optics_cache=optics_cache,
                        tmp_dir=tmp_dir,
                        source=source,
                        concurrency=concurrency,
                    )

                    all_points.extend(batch_points)
                    progress.advance(task, advance=len(batch_keys))

        finally:
            # Clean up temp dir
            shutil.rmtree(tmp_dir, ignore_errors=True)

        no_gps = len(all_keys) - len(all_points)
        print(f"\nExtracted {len(all_points)} points with GPS ({no_gps} skipped, no GPS)")
        print(f"Optics cache: {optics_cache.stats()} entries")

        if not all_points:
            print("No points to publish")
            return

        # Step 5: Fetch elevation
        coords = [(p["lat"], p["lng"]) for p in all_points]
        print(f"\nFetching elevation for {len(coords)} points...")

        async with ElevationClient() as elev_client:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
            ) as progress:
                task = progress.add_task("Fetching elevations...", total=len(coords))

                def update_progress(completed, total):
                    progress.update(task, completed=completed)

                results = await elev_client.get_elevations(
                    coords, progress_callback=update_progress
                )

        with_elevation = sum(1 for r in results if r.elevation is not None)
        cached = sum(1 for r in results if r.cached)
        print(f"Elevation: {with_elevation}/{len(results)} resolved ({cached} from cache)")

        # Attach elevation to points
        for point, result in zip(all_points, results):
            point["elevation"] = result.elevation

        if dry_run:
            print(f"\n[DRY RUN] Would publish {len(all_points)} points to NATS")
            # Show sample
            for p in all_points[:5]:
                elev = f"{p['elevation']:.0f}m" if p["elevation"] else "none"
                optics_str = ""
                if p["optics"] and p["optics"].light_value:
                    optics_str = f" EV:{p['optics'].light_value}"
                print(f"  {p['key']} ({p['lat']:.4f}, {p['lng']:.4f}) elev={elev}{optics_str}")
            if len(all_points) > 5:
                print(f"  ... and {len(all_points) - 5} more")
            return

        # Step 6: Publish to NATS
        print(f"\nPublishing {len(all_points)} points to NATS...")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Publishing...", total=len(all_points))

            for point in all_points:
                key = point["key"]
                key_hex = key.replace("img_", "").rsplit(".", 1)[0]

                msg = {
                    "id": key_hex,
                    "lat": round(point["lat"], 5),
                    "lng": round(point["lng"], 5),
                    "timestamp": point["timestamp"] or datetime.now().isoformat(),
                    "image": key,
                    "source": source,
                    "tags": [],
                }

                if point["elevation"] is not None:
                    msg["elevation"] = point["elevation"]

                optics = point["optics"]
                if optics:
                    if optics.light_value is not None:
                        msg["light_value"] = optics.light_value
                    if optics.iso is not None:
                        msg["iso"] = optics.iso
                    if optics.shutter_speed is not None:
                        msg["shutter_speed"] = optics.shutter_speed
                    if optics.aperture is not None:
                        msg["aperture"] = optics.aperture
                    if optics.focal_length_35mm is not None:
                        msg["focal_length_35mm"] = optics.focal_length_35mm

                await js.publish("trips.point", json.dumps(msg).encode())
                progress.advance(task)

        # Step 7: Final stats
        queue_stats = queue.get_stats()
        print(f"\nDone! Published {len(all_points)} points to NATS")
        print(f"  With elevation: {with_elevation}")
        print(f"  Queue DB: {queue_stats.get(UploadStatus.COMPLETED.value, 0)} completed")

    finally:
        await nc.close()
```

**Step 4: Commit**

```bash
git add scripts/publish-trip-images/main.py
git commit -m "feat(publish-trip-images): add rebuild command to recover data from SeaweedFS"
```

---

### Task 5: Run format and Bazel build check

**Files:**
- Possibly modify: `scripts/publish-trip-images/main.py` (formatting), `scripts/publish-trip-images/BUILD` (buildifier)

**Step 1: Run formatters**

Run: `cd /tmp/claude-worktrees/rebuild-nats && format`
Expected: Formatters run, possibly reformats BUILD file or Python code.

**Step 2: Run Bazel build**

Run: `cd /tmp/claude-worktrees/rebuild-nats && bazel build //scripts/publish-trip-images:main`
Expected: Build succeeds. If it fails, fix import issues or missing deps.

**Step 3: Run existing tests**

Run: `cd /tmp/claude-worktrees/rebuild-nats && bazel test //scripts/publish-trip-images:...`
Expected: Existing tests still pass (no behavioral changes to existing code).

**Step 4: Commit if formatters changed anything**

```bash
git add -u
git commit -m "style(publish-trip-images): format rebuild command"
```

---

### Task 6: Run Gazelle and Semgrep

**Step 1: Regenerate BUILD files**

Run: `cd /tmp/claude-worktrees/rebuild-nats && bazel run gazelle`
Expected: BUILD files updated if needed.

**Step 2: Run Semgrep**

Run: `cd /tmp/claude-worktrees/rebuild-nats && bazel test //scripts/publish-trip-images:main_semgrep_test`
Expected: Passes. If it flags issues (e.g., broad exception catches), fix them.

**Step 3: Commit if anything changed**

```bash
git add -u
git commit -m "build(publish-trip-images): update BUILD files for rebuild command"
```

---

### Task 7: Push and create PR

**Step 1: Push branch**

```bash
cd /tmp/claude-worktrees/rebuild-nats
git push -u origin fix/rebuild-nats-from-seaweedfs
```

**Step 2: Create PR**

```bash
gh pr create \
  --title "feat(publish-trip-images): add rebuild command to recover NATS data from SeaweedFS" \
  --body "$(cat <<'EOF'
## Summary

- Adds `rebuild` command to `scripts/publish-trip-images` that recovers trip metadata from SeaweedFS images when NATS stream data is lost
- Downloads images in batches (80 at a time, ~440MB peak disk) to extract EXIF metadata
- Fetches elevation data from NRCan CDEM API with SQLite caching
- Populates `publish_queue.db` and publishes enriched points to NATS
- Fixes NATS stream `max_age` from 30d to unlimited to prevent recurrence

## Context

The NATS `trips` stream had `max_age: 30d`. Last data was published 2026-01-07, so all messages expired. The trips API serves from this stream — with 0 messages, trips.jomcgi.dev shows a blank page. All 4,878 images are intact in SeaweedFS.

## Test plan

- [ ] `bazel build //scripts/publish-trip-images:main` succeeds
- [ ] `bazel test //scripts/publish-trip-images:...` passes
- [ ] Run `rebuild --dry-run` with port-forward to verify S3 listing and EXIF extraction
- [ ] Run `rebuild` to restore live data and verify trips.jomcgi.dev loads

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
