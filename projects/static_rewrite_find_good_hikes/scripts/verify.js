// scripts/verify.js - Master verification script
const { spawn } = require('child_process');
const path = require('path');

const PROJECT_DIR = path.resolve(__dirname, '..');
const VERIFIER_SCRIPT = path.join(__dirname, 'capture-logs.js');

async function runVerification() {
  console.log('🚀 Starting verification process...');
  
  let serverProcess;
  
  // Cleanup function
  const cleanup = () => {
    if (serverProcess && !serverProcess.killed) {
      console.log('🧹 Cleaning up server process...');
      serverProcess.kill('SIGTERM');
    }
  };

  // Set up cleanup on exit
  process.on('exit', cleanup);
  process.on('SIGINT', cleanup);
  process.on('SIGTERM', cleanup);

  try {
    // Start the server
    console.log('📡 Starting server...');
    serverProcess = spawn('python3', ['-m', 'http.server', '8000'], {
      cwd: path.join(PROJECT_DIR, 'public'),
      stdio: ['ignore', 'pipe', 'pipe']
    });

    // Wait for server to start
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Server startup timeout')), 10000);
      
      serverProcess.stdout.on('data', (data) => {
        const output = data.toString();
        console.log('Server stdout:', output.trim());
        if (output.includes('Serving HTTP') || output.includes('HTTP server')) {
          clearTimeout(timeout);
          resolve();
        }
      });
      
      serverProcess.stderr.on('data', (data) => {
        const errorOutput = data.toString();
        console.error('Server stderr:', errorOutput.trim());
        if (errorOutput.includes('Address already in use')) {
          clearTimeout(timeout);
          reject(new Error('Port 8000 is already in use'));
        }
      });
      
      serverProcess.on('error', (err) => {
        clearTimeout(timeout);
        reject(err);
      });
      
      // Also resolve after a short delay if we don't see the expected message
      setTimeout(() => {
        console.log('No server startup message seen, assuming server started');
        clearTimeout(timeout);
        resolve();
      }, 3000);
    });

    console.log('⏳ Server started, waiting 2 seconds for stability...');
    await new Promise(resolve => setTimeout(resolve, 2000));

    // Run the log capture
    console.log('🔍 Capturing console logs...');
    const captureProcess = spawn('node', [VERIFIER_SCRIPT], {
      cwd: PROJECT_DIR,
      stdio: 'inherit'
    });

    await new Promise((resolve, reject) => {
      captureProcess.on('close', (code) => {
        if (code === 0) {
          resolve();
        } else {
          reject(new Error(`Log capture failed with code ${code}`));
        }
      });
    });

    console.log('✅ Verification complete!');

  } catch (error) {
    console.error('❌ Verification failed:', error.message);
    process.exit(1);
  } finally {
    cleanup();
  }
}

runVerification();