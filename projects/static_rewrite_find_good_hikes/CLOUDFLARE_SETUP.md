# Cloudflare Setup Guide

This guide explains how to deploy Find Good Hikes using Cloudflare Pages (for the website) and R2 (for data storage).

## Architecture

- **Cloudflare Pages**: Hosts the static HTML/JS/CSS website
- **Cloudflare R2**: Stores the hourly-updated JSON data files
- **GitHub Actions**: Updates R2 with fresh weather data every hour

## Prerequisites

1. Cloudflare account (free tier is sufficient)
2. GitHub repository with this code
3. Domain name (optional, can use Cloudflare's provided domain)

## Step 1: Create R2 Bucket

1. Log into Cloudflare Dashboard
2. Go to R2 > Create bucket
3. Name it `jomcgi-hikes`
4. Settings:
   - Location: Automatic
   - Storage Class: Standard
5. After creation, go to Settings > Public access
6. Enable public access and note the public URL

## Step 2: Create R2 API Token

1. Go to R2 > Manage R2 API tokens
2. Create a new token with:
   - Permissions: Object Read & Write
   - Bucket: jomcgi-hikes
   - TTL: No expiration
3. Save the credentials:
   - Access Key ID
   - Secret Access Key
   - Account ID (from your Cloudflare dashboard URL)

## Step 3: Configure GitHub Secrets

In your GitHub repository, go to Settings > Secrets and add:

- `CLOUDFLARE_S3_ACCESS_KEY_ID`: From R2 API token
- `CLOUDFLARE_S3_ACCESS_KEY_SECRET`: From R2 API token
- `CLOUDFLARE_S3_ENDPOINT`: The S3 API endpoint (e.g., `https://<account-id>.r2.cloudflarestorage.com`)
- `CLOUDFLARE_R2_PUBLIC_URL`: The public URL from R2 bucket settings (e.g., `https://pub-abc123.r2.dev`)

Note: The bucket name is configured separately in the workflow as `jomcgi-hikes`

## Step 4: Deploy to Cloudflare Pages

1. Go to Cloudflare Pages > Create a project
2. Connect to your GitHub repository
3. Configuration:
   - Production branch: `main`
   - Build command: (leave empty - no build needed)
   - Build output directory: `projects/static_rewrite_find_good_hikes/public`
   - Root directory: `/`
4. Environment variables: None needed
5. Deploy!

## Step 5: Update Website Configuration

1. Edit `public/config.js`:
   ```javascript
   window.HIKES_CONFIG = {
       dataUrl: 'https://your-r2-public-url.r2.dev/',  // Your actual R2 URL
       useLocalData: window.location.hostname === 'localhost',
       cacheMinutes: 60
   };
   ```

2. Commit and push - Cloudflare Pages will auto-deploy

## Step 6: Configure Custom Domain (Optional)

1. In Cloudflare Pages > Custom domains
2. Add your domain
3. Follow DNS configuration instructions

## Step 7: Enable CORS on R2 (Important!)

1. Go to R2 > your bucket > Settings > CORS
2. Add this policy:
   ```json
   [
     {
       "AllowedOrigins": ["*"],
       "AllowedMethods": ["GET", "HEAD"],
       "AllowedHeaders": ["*"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```

## Monitoring

- **Website deploys**: Check Cloudflare Pages dashboard
- **Data updates**: Check GitHub Actions runs
- **R2 usage**: Monitor in R2 dashboard (free tier: 10GB storage, 1M requests/month)

## Costs

With normal usage, everything should fit in Cloudflare's free tier:
- Pages: Unlimited sites, 500 builds/month
- R2: 10GB storage, 1M Class A operations, 10M Class B operations
- Bandwidth: Unlimited through Cloudflare CDN

## Troubleshooting

**Data not loading?**
- Check browser console for CORS errors
- Verify R2 public access is enabled
- Check R2 public URL in config.js

**GitHub Actions failing?**
- Verify all secrets are set correctly
- Check Actions logs for specific errors
- Ensure R2 API token has write permissions

**Old data showing?**
- Browser cache - try hard refresh (Ctrl+F5)
- Check CloudFlare cache settings
- Verify GitHub Actions are running successfully