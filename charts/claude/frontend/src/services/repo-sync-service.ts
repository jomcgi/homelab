import { exec } from "child_process";
import { promisify } from "util";
import * as fs from "fs/promises";
import * as path from "path";
import { createLogger, type Logger } from "./logger.js";

const execAsync = promisify(exec);

/**
 * Configuration for a synced repository
 */
export interface RepoSyncConfig {
  /** Git remote URL (e.g., https://github.com/user/repo) */
  url: string;
  /** Local path where the repo should be cloned */
  localPath: string;
  /** Branch to track (default: main) */
  branch?: string;
  /** Sync interval in milliseconds (default: 60000 = 1 minute) */
  syncIntervalMs?: number;
}

/**
 * Status of a synced repository
 */
export interface RepoSyncStatus {
  url: string;
  localPath: string;
  branch: string;
  lastFetchTime?: Date;
  lastFetchError?: string;
  localHead?: string;
  remoteHead?: string;
  isCloned: boolean;
  isSyncing: boolean;
}

/**
 * Service for managing git repository synchronization.
 *
 * Replaces the git-sync sidecar with simpler custom logic that:
 * - Clones the repo on startup if not present
 * - Runs `git fetch origin` periodically to keep refs fresh
 * - Allows worktrees to be created without interference
 *
 * Unlike git-sync, this service:
 * - Does NOT use worktrees internally for sync
 * - Does NOT reset the working directory
 * - Only fetches to update remote refs
 */
export class RepoSyncService {
  private logger: Logger;
  private repos: Map<string, RepoSyncConfig> = new Map();
  private statuses: Map<string, RepoSyncStatus> = new Map();
  private syncIntervals: Map<string, NodeJS.Timeout> = new Map();
  private isInitialized = false;

  constructor() {
    this.logger = createLogger("RepoSyncService");
  }

  /**
   * Add a repository to sync
   */
  addRepo(config: RepoSyncConfig): void {
    const key = config.localPath;
    this.repos.set(key, {
      ...config,
      branch: config.branch || "main",
      syncIntervalMs: config.syncIntervalMs || 60000,
    });
    this.statuses.set(key, {
      url: config.url,
      localPath: config.localPath,
      branch: config.branch || "main",
      isCloned: false,
      isSyncing: false,
    });
  }

  /**
   * Initialize all configured repositories
   */
  async initialize(): Promise<void> {
    if (this.isInitialized) {
      this.logger.warn("RepoSyncService already initialized");
      return;
    }

    this.logger.info("Initializing RepoSyncService", {
      repoCount: this.repos.size,
    });

    for (const [key, config] of this.repos) {
      try {
        await this.initializeRepo(config);
        this.startSyncInterval(key, config);
      } catch (error) {
        this.logger.error("Failed to initialize repository", error, {
          localPath: config.localPath,
          url: config.url,
        });
        // Continue with other repos
      }
    }

    this.isInitialized = true;
    this.logger.info("RepoSyncService initialized successfully");
  }

  /**
   * Initialize a single repository - clone if needed
   */
  private async initializeRepo(config: RepoSyncConfig): Promise<void> {
    const status = this.statuses.get(config.localPath)!;

    // Check if repo already exists
    const gitDir = path.join(config.localPath, ".git");
    let exists = false;

    try {
      await fs.access(gitDir);
      exists = true;
    } catch {
      exists = false;
    }

    if (exists) {
      this.logger.info("Repository already exists, verifying remote", {
        localPath: config.localPath,
      });

      // Verify the remote URL matches
      try {
        const { stdout } = await execAsync("git remote get-url origin", {
          cwd: config.localPath,
        });
        const currentUrl = stdout.trim();

        if (currentUrl !== config.url) {
          this.logger.warn("Remote URL mismatch, updating", {
            currentUrl,
            expectedUrl: config.url,
          });
          await execAsync(`git remote set-url origin "${config.url}"`, {
            cwd: config.localPath,
          });
        }

        status.isCloned = true;

        // Do initial fetch
        await this.fetchRepo(config);
      } catch (error) {
        this.logger.error("Failed to verify existing repository", error, {
          localPath: config.localPath,
        });
        throw error;
      }
    } else {
      this.logger.info("Cloning repository", {
        url: config.url,
        localPath: config.localPath,
        branch: config.branch,
      });

      // Ensure parent directory exists
      const parentDir = path.dirname(config.localPath);
      await fs.mkdir(parentDir, { recursive: true });

      // Clone the repository
      try {
        await execAsync(
          `git clone --branch "${config.branch}" "${config.url}" "${config.localPath}"`,
          {
            env: {
              ...process.env,
              GIT_TERMINAL_PROMPT: "0", // Disable interactive prompts
            },
          },
        );

        status.isCloned = true;
        this.logger.info("Repository cloned successfully", {
          localPath: config.localPath,
        });

        // Get initial HEAD
        const { stdout } = await execAsync("git rev-parse HEAD", {
          cwd: config.localPath,
        });
        status.localHead = stdout.trim();
      } catch (error) {
        this.logger.error("Failed to clone repository", error, {
          url: config.url,
          localPath: config.localPath,
        });
        throw error;
      }
    }
  }

  /**
   * Fetch updates from remote
   */
  private async fetchRepo(config: RepoSyncConfig): Promise<void> {
    const status = this.statuses.get(config.localPath)!;

    if (status.isSyncing) {
      this.logger.debug("Fetch already in progress, skipping", {
        localPath: config.localPath,
      });
      return;
    }

    status.isSyncing = true;

    try {
      this.logger.debug("Fetching from remote", {
        localPath: config.localPath,
        branch: config.branch,
      });

      // Fetch all refs from origin
      await execAsync("git fetch origin", {
        cwd: config.localPath,
        env: {
          ...process.env,
          GIT_TERMINAL_PROMPT: "0",
        },
      });

      // Get local and remote HEAD
      const [localResult, remoteResult] = await Promise.all([
        execAsync("git rev-parse HEAD", { cwd: config.localPath }),
        execAsync(`git rev-parse origin/${config.branch}`, {
          cwd: config.localPath,
        }),
      ]);

      status.localHead = localResult.stdout.trim();
      status.remoteHead = remoteResult.stdout.trim();
      status.lastFetchTime = new Date();
      status.lastFetchError = undefined;

      // Log if local is behind remote
      if (status.localHead !== status.remoteHead) {
        this.logger.info("Repository has new commits available", {
          localPath: config.localPath,
          localHead: status.localHead.substring(0, 8),
          remoteHead: status.remoteHead.substring(0, 8),
        });
      } else {
        this.logger.debug("Repository is up to date", {
          localPath: config.localPath,
          head: status.localHead.substring(0, 8),
        });
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error);
      status.lastFetchError = errorMessage;
      this.logger.error("Failed to fetch from remote", error, {
        localPath: config.localPath,
      });
    } finally {
      status.isSyncing = false;
    }
  }

  /**
   * Start the periodic sync interval for a repo
   */
  private startSyncInterval(key: string, config: RepoSyncConfig): void {
    // Clear any existing interval
    const existing = this.syncIntervals.get(key);
    if (existing) {
      clearInterval(existing);
    }

    const intervalMs = config.syncIntervalMs || 60000;

    this.logger.info("Starting sync interval", {
      localPath: config.localPath,
      intervalMs,
    });

    const interval = setInterval(() => {
      this.fetchRepo(config).catch((error) => {
        this.logger.error("Periodic fetch failed", error, {
          localPath: config.localPath,
        });
      });
    }, intervalMs);

    this.syncIntervals.set(key, interval);
  }

  /**
   * Get status of all repositories
   */
  getAllStatuses(): RepoSyncStatus[] {
    return Array.from(this.statuses.values());
  }

  /**
   * Get status of a specific repository
   */
  getStatus(localPath: string): RepoSyncStatus | undefined {
    return this.statuses.get(localPath);
  }

  /**
   * Force a fetch for a specific repository
   */
  async forceFetch(localPath: string): Promise<void> {
    const config = this.repos.get(localPath);
    if (!config) {
      throw new Error(`Repository not found: ${localPath}`);
    }
    await this.fetchRepo(config);
  }

  /**
   * Stop all sync intervals and cleanup
   */
  stop(): void {
    this.logger.info("Stopping RepoSyncService");

    for (const [key, interval] of this.syncIntervals) {
      clearInterval(interval);
      this.logger.debug("Cleared sync interval", { key });
    }

    this.syncIntervals.clear();
    this.isInitialized = false;
  }
}

// Singleton instance
let repoSyncServiceInstance: RepoSyncService | undefined;

/**
 * Get or create the RepoSyncService singleton
 */
export function getRepoSyncService(): RepoSyncService {
  if (!repoSyncServiceInstance) {
    repoSyncServiceInstance = new RepoSyncService();
  }
  return repoSyncServiceInstance;
}

/**
 * Reset the singleton (for testing)
 */
export function resetRepoSyncService(): void {
  if (repoSyncServiceInstance) {
    repoSyncServiceInstance.stop();
    repoSyncServiceInstance = undefined;
  }
}
