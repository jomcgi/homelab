#!/usr/bin/env fish

# Setup user.bazelrc with BuildBuddy remote cache if API key is available
# This script is sourced automatically when fish shell starts in session pods

set -l workspace_dir /workspace/session

# Only run if we're in the workspace and BUILDBUDDY_API_KEY is set
if test -d $workspace_dir; and set -q BUILDBUDDY_API_KEY
    set -l bazelrc_path $workspace_dir/user.bazelrc

    # Create user.bazelrc if it doesn't exist or is outdated
    if not test -f $bazelrc_path; or not grep -q "buildbuddy-api-key" $bazelrc_path
        echo "# Auto-generated user.bazelrc for BuildBuddy remote cache" > $bazelrc_path
        echo "# This file enables fast Bazel builds with remote caching" >> $bazelrc_path
        echo "" >> $bazelrc_path
        echo "# BuildBuddy remote cache and build execution" >> $bazelrc_path
        echo "build --bes_results_url=https://app.buildbuddy.io/invocation/" >> $bazelrc_path
        echo "build --bes_backend=grpcs://remote.buildbuddy.io" >> $bazelrc_path
        echo "build --remote_cache=grpcs://remote.buildbuddy.io" >> $bazelrc_path
        echo "build --remote_header=x-buildbuddy-api-key=$BUILDBUDDY_API_KEY" >> $bazelrc_path
        echo "build --remote_cache_compression" >> $bazelrc_path
        echo "" >> $bazelrc_path
        echo "✅ BuildBuddy remote cache configured! Bazel builds will be fast."
    end
end
