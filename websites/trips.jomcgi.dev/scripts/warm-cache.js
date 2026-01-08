#!/usr/bin/env node

/**
 * Cache Warming Script for trips.jomcgi.dev
 *
 * Fetches all trip points and pre-warms the Cloudflare cache by requesting
 * each image variant (thumb and display).
 *
 * Usage:
 *   node scripts/warm-cache.js [--dry-run] [--force] [--concurrency=N]
 *
 * Options:
 *   --dry-run      Only check cache status, don't warm (HEAD requests only)
 *   --force        Request all images even if already cached
 *   --concurrency  Number of parallel requests (default: 5, be gentle to origin)
 */

const API_URL = "https://api.jomcgi.dev/trips/api/points";
const IMAGE_BASE_URL = "https://img.jomcgi.dev";

// Image variants to warm
const VARIANTS = [
  { name: "thumb", path: "/trips/thumb/" },
  { name: "display", path: "/trips/display/" },
];

async function fetchPoints() {
  console.log("Fetching points from API...");
  const response = await fetch(API_URL);
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  const data = await response.json();
  console.log(`Found ${data.points.length} points\n`);
  return data.points;
}

async function checkCache(url) {
  try {
    const response = await fetch(url, { method: "HEAD" });
    const cacheStatus = response.headers.get("cf-cache-status");
    return { cached: cacheStatus === "HIT", status: cacheStatus };
  } catch (error) {
    return { cached: false, status: "ERROR" };
  }
}

async function warmImage(url) {
  try {
    const response = await fetch(url);
    const cacheStatus = response.headers.get("cf-cache-status");
    return { success: true, status: cacheStatus };
  } catch (error) {
    return { success: false, status: "ERROR", error: error.message };
  }
}

async function processImage(image, variant, stats, options) {
  const url = `${IMAGE_BASE_URL}${variant.path}${image}`;

  // Check cache status
  const { cached, status } = await checkCache(url);

  if (cached) {
    stats.hits++;
    return { skipped: true, status };
  }

  stats.misses++;

  // In dry-run mode, just report the miss
  if (options.dryRun) {
    return { skipped: true, status, needsWarm: true };
  }

  // Skip warming if not forced and already checked
  if (!options.force && cached) {
    return { skipped: true, status };
  }

  // Warm the cache
  const result = await warmImage(url);
  if (result.success) {
    stats.warmed++;
  } else {
    stats.errors++;
  }
  return result;
}

async function processWithConcurrency(items, concurrency, processor) {
  const results = [];
  for (let i = 0; i < items.length; i += concurrency) {
    const batch = items.slice(i, i + concurrency);
    const batchResults = await Promise.all(batch.map(processor));
    results.push(...batchResults);
  }
  return results;
}

function formatDuration(ms) {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

async function main() {
  const args = process.argv.slice(2);
  const dryRun = args.includes("--dry-run");
  const force = args.includes("--force");
  const concurrencyArg = args.find((a) => a.startsWith("--concurrency="));
  const concurrency = concurrencyArg
    ? parseInt(concurrencyArg.split("=")[1])
    : 5;

  const options = { dryRun, force };

  console.log("=".repeat(60));
  console.log("Cache Warming Script for trips.jomcgi.dev");
  console.log("=".repeat(60));
  if (dryRun) {
    console.log("Mode: DRY RUN (check only, no warming)");
  } else if (force) {
    console.log("Mode: Force (re-warm all)");
  } else {
    console.log("Mode: Warm uncached images only");
  }
  console.log(`Concurrency: ${concurrency} parallel requests`);
  console.log("");

  const startTime = Date.now();

  // Fetch all points
  const points = await fetchPoints();

  // Get unique images
  const images = [...new Set(points.map((p) => p.image).filter(Boolean))];
  console.log(`Unique images: ${images.length}`);
  console.log(`Variants: ${VARIANTS.map((v) => v.name).join(", ")}`);
  console.log(`Total requests: ${images.length * VARIANTS.length}\n`);

  // Process each variant
  for (const variant of VARIANTS) {
    console.log(
      `\n${dryRun ? "Checking" : "Warming"} ${variant.name} images...`,
    );
    console.log("-".repeat(40));

    const stats = { hits: 0, misses: 0, warmed: 0, errors: 0 };
    let processed = 0;

    await processWithConcurrency(images, concurrency, async (image) => {
      const result = await processImage(image, variant, stats, options);
      processed++;

      // Progress update every 100 images
      if (processed % 100 === 0 || processed === images.length) {
        const pct = ((processed / images.length) * 100).toFixed(1);
        if (dryRun) {
          process.stdout.write(
            `\r  Progress: ${processed}/${images.length} (${pct}%) | ` +
              `Cached: ${stats.hits} | Need warming: ${stats.misses}`,
          );
        } else {
          process.stdout.write(
            `\r  Progress: ${processed}/${images.length} (${pct}%) | ` +
              `Cached: ${stats.hits} | Warmed: ${stats.warmed} | Errors: ${stats.errors}`,
          );
        }
      }

      return result;
    });

    console.log("\n");
    console.log(`  ${variant.name} summary:`);
    console.log(`    Already cached: ${stats.hits}`);
    if (dryRun) {
      console.log(`    Need warming: ${stats.misses}`);
    } else {
      console.log(`    Newly warmed: ${stats.warmed}`);
      console.log(`    Errors: ${stats.errors}`);
    }
  }

  const duration = Date.now() - startTime;
  console.log("\n" + "=".repeat(60));
  console.log(`Completed in ${formatDuration(duration)}`);
  console.log("=".repeat(60));
}

main().catch((error) => {
  console.error("Error:", error.message);
  process.exit(1);
});
