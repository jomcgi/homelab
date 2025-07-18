Summary of Key Issues and Solutions
Based on comparing your operator with the Kubernetes sample-controller, here are the main issues causing ungraceful shutdown:
1. Complex Signal Handler Anti-pattern
Your setupSignalHandlers function creates a goroutine that waits for context cancellation, then creates a new context. This pattern can cause race conditions and prevent proper cleanup.
Solution: Remove custom signal handlers and use the standard controller-runtime pattern.
2. Blocking TunnelInitializer
The TunnelInitializer.Start() method blocks with <-ctx.Done(), which ties up a manager goroutine.
Solution: Make initialization non-blocking by running it in a goroutine.
3. Missing Graceful Shutdown Configuration
The manager lacks proper shutdown timeout configuration.
Solution: Add GracefulShutdownTimeout to manager options.
4. Cleanup Not Integrated with Manager Lifecycle
Emergency cleanup runs outside the manager's control flow.
Solution: Use a CleanupManager runnable that integrates with the manager.
Quick Fixes to Implement

Replace signal handling in main.go (see "Minimal Fix: Signal Handling Patch" artifact)
Add GracefulShutdownTimeout to manager options
Make TunnelInitializer non-blocking
Add CleanupManager runnable for shutdown handling
Reduce terminationGracePeriodSeconds from 1200 to 300 seconds
Simplify Helm post-delete hooks - remove complex validation