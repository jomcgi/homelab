# FreshRSS Backup and Migration Guide

## Data Persistence Guarantees

### What Persists
- **RSS feeds and subscriptions** ✅
- **Feed articles and history** ✅
- **User settings and preferences** ✅
- **Read/unread/starred states** ✅
- **Installed extensions** ✅

### Storage Architecture
- **Longhorn Storage**: 3x replication across cluster nodes
- **Persistent Volume Claims**: Survive pod restarts/crashes
- **Reclaim Policy**: `Delete` (volumes deleted when PVC is deleted)

## Backup Strategies

### 1. Full User Backup (Recommended)

Export everything for a user (feeds, articles, settings):

```bash
# Create backup
kubectl exec -n freshrss deployment/freshrss -- \
  php cli/export-zip-for-user.php --user <username> > freshrss-backup-$(date +%Y%m%d).zip

# List what's included
unzip -l freshrss-backup-*.zip
```

### 2. OPML Export (Feeds Only)

Export just your feed subscriptions:

```bash
# Export OPML
kubectl exec -n freshrss deployment/freshrss -- \
  php cli/export-opml-for-user.php --user <username> > feeds-$(date +%Y%m%d).opml

# Import via web UI: Settings → Subscription Management → Import
```

### 3. Database Backup

For SQLite (default configuration):

```bash
# Export SQLite database for a user
kubectl exec -n freshrss deployment/freshrss -- \
  php cli/export-sqlite-for-user.php --user <username> > freshrss-db-$(date +%Y%m%d).sqlite

# Or backup all users
kubectl exec -n freshrss deployment/freshrss -- \
  php cli/db-backup.php
```

### 4. Volume Snapshots (Longhorn)

Use Longhorn's built-in snapshot feature:

```bash
# Create Longhorn snapshot via UI
# Navigate to: https://longhorn.jomcgi.dev
# Select volume → Take Snapshot
# Set recurring snapshots for automatic backups
```

## Migration: Dev → Prod

### Method 1: Using Backup/Restore (Recommended)

```bash
# 1. Export from dev
kubectl exec -n freshrss deployment/freshrss -- \
  php cli/export-zip-for-user.php --user admin > freshrss-dev-backup.zip

# 2. Deploy prod overlay
# Create overlays/prod/freshrss/ with production values

# 3. Copy backup to prod pod
PROD_POD=$(kubectl get pod -n freshrss-prod -l app.kubernetes.io/name=freshrss -o jsonpath='{.items[0].metadata.name}')
kubectl cp freshrss-dev-backup.zip freshrss-prod/${PROD_POD}:/tmp/backup.zip

# 4. Restore in prod (use web UI or manual extraction)
```

### Method 2: OPML Import (Feeds Only)

```bash
# 1. Export OPML from dev
kubectl exec -n freshrss deployment/freshrss -- \
  php cli/export-opml-for-user.php --user admin > feeds.opml

# 2. Import in prod via web UI
# Settings → Subscription Management → Import → feeds.opml
```

### Method 3: Volume Clone (Advanced)

```bash
# 1. Create Longhorn snapshot of dev volume
# 2. Clone snapshot to new volume in prod namespace
# 3. Update prod PVC to use cloned volume
# See: https://longhorn.io/docs/latest/snapshots-and-backups/
```

## Automated Backups

### Option 1: CronJob for OPML Backups

Create a Kubernetes CronJob:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: freshrss-backup
  namespace: freshrss
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: backup
            image: freshrss/freshrss:latest
            command:
            - /bin/sh
            - -c
            - php cli/export-opml-for-user.php --user admin > /backup/feeds-$(date +%Y%m%d).opml
            volumeMounts:
            - name: backup
              mountPath: /backup
            - name: data
              mountPath: /var/www/FreshRSS/data
          volumes:
          - name: backup
            persistentVolumeClaim:
              claimName: freshrss-backup  # Create separate PVC for backups
          - name: data
            persistentVolumeClaim:
              claimName: freshrss-data
          restartPolicy: OnFailure
```

### Option 2: Longhorn Recurring Snapshots

Configure in Longhorn UI:
1. Navigate to Volume → `pvc-xxxxx` (freshrss-data)
2. Click "Create Recurring Job"
3. Set schedule: `0 2 * * *` (daily at 2 AM)
4. Retention: 7 snapshots
5. Enable backup to S3 for off-cluster storage

## Disaster Recovery

### Scenario 1: Accidental Pod Deletion
**Impact:** None - PVC persists
```bash
# Pod will auto-recreate via deployment
kubectl get pods -n freshrss -w
```

### Scenario 2: Accidental PVC Deletion
**Impact:** Total data loss (if no backups)
**Recovery:**
```bash
# Restore from backup
kubectl exec -n freshrss deployment/freshrss -- \
  php cli/import-for-user.php --user admin --filename /tmp/backup.zip
```

### Scenario 3: Node Failure
**Impact:** None - Longhorn replicates across 3 nodes
```bash
# Longhorn automatically fails over to healthy replicas
kubectl get pv | grep freshrss
```

### Scenario 4: Cluster Loss
**Impact:** Depends on off-cluster backups
**Recovery:**
- Restore Longhorn backups from S3
- Or restore from exported OPML/ZIP files

## Best Practices

### Daily Operations
- ✅ **Enable Longhorn recurring snapshots** (hourly or daily)
- ✅ **Export OPML weekly** for feed subscriptions
- ✅ **Test restore procedure** quarterly
- ✅ **Monitor Longhorn replica health** via dashboard

### Before Major Changes
- ✅ **Export full backup** before upgrades
- ✅ **Create Longhorn snapshot** before migrations
- ✅ **Verify backup integrity** by testing restore

### Production Deployment
- ✅ **Enable Longhorn backups to S3** for off-cluster storage
- ✅ **Set up automated CronJob backups**
- ✅ **Document restore procedures**
- ✅ **Test disaster recovery plan**

## Common CLI Commands

```bash
# List all FreshRSS CLI tools
kubectl exec -n freshrss deployment/freshrss -- ls -la /var/www/FreshRSS/cli/

# List users
kubectl exec -n freshrss deployment/freshrss -- php cli/list-users.php

# Create manual backup
kubectl exec -n freshrss deployment/freshrss -- \
  php cli/export-zip-for-user.php --user admin > backup.zip

# Export OPML
kubectl exec -n freshrss deployment/freshrss -- \
  php cli/export-opml-for-user.php --user admin > feeds.opml

# Database backup (all users)
kubectl exec -n freshrss deployment/freshrss -- php cli/db-backup.php

# Check disk usage
kubectl exec -n freshrss deployment/freshrss -- du -sh /var/www/FreshRSS/data
```

## Monitoring Storage

```bash
# Check PVC status
kubectl get pvc -n freshrss

# Check Longhorn volume health
# Navigate to: https://longhorn.jomcgi.dev
# Check: Volume → Health Status → Number of Replicas

# Check disk usage
kubectl exec -n freshrss deployment/freshrss -- df -h /var/www/FreshRSS/data
```

## Additional Resources

- [FreshRSS CLI Documentation](https://freshrss.github.io/FreshRSS/en/admins/11_Command_Line_Interface.html)
- [Longhorn Backup and Restore](https://longhorn.io/docs/latest/snapshots-and-backups/)
- [Kubernetes Volume Snapshots](https://kubernetes.io/docs/concepts/storage/volume-snapshots/)
