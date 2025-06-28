// scripts/capture-logs.js
const puppeteer = require('puppeteer');

// The URL of the locally running static server
const TARGET_URL = 'http://localhost:8000';
// How long to wait on the page before exiting (in milliseconds)
const WAIT_TIME_MS = 5000;

async function captureConsoleLogs() {
  const capturedLogs = [];
  let browser;

  try {
    // Launch a new headless browser instance
    browser = await puppeteer.launch({ 
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox'] // For codespace compatibility
    });
    const page = await browser.newPage();

    // Set up the event listener for console messages
    page.on('console', async (msg) => {
      const type = msg.type();
      const text = msg.text();
      const location = msg.location();

      // For complex arguments like objects or arrays, resolve the JSHandle
      const args = await Promise.all(
        msg.args().map(arg => arg.jsonValue().catch(() => arg.toString()))
      );

      const logEntry = {
        type: type, // 'log', 'warning', 'error', 'info', etc.
        text: text, // The formatted message string
        location: { // Source location of the console call
          url: location.url,
          lineNumber: location.lineNumber,
          columnNumber: location.columnNumber,
        },
        args: args, // The raw arguments passed to the console call
        timestamp: new Date().toISOString(),
      };
      capturedLogs.push(logEntry);
    });

    // Listen for JavaScript errors that might not be logged to console
    page.on('pageerror', (err) => {
      const errorEntry = {
        type: 'pageerror',
        text: err.message,
        location: { url: TARGET_URL, lineNumber: 0, columnNumber: 0 },
        args: [err.message],
        timestamp: new Date().toISOString(),
      };
      capturedLogs.push(errorEntry);
    });

    // Listen for failed network requests
    page.on('requestfailed', (request) => {
      const networkErrorEntry = {
        type: 'requestfailed',
        text: `Failed to load: ${request.url()}`,
        location: { url: request.url(), lineNumber: 0, columnNumber: 0 },
        args: [request.failure().errorText],
        timestamp: new Date().toISOString(),
      };
      capturedLogs.push(networkErrorEntry);
    });

    console.log(`Navigating to ${TARGET_URL}...`);
    
    // Navigate to the target URL
    await page.goto(TARGET_URL, { 
      waitUntil: 'networkidle2',
      timeout: 10000 
    });

    console.log(`Waiting ${WAIT_TIME_MS}ms for page to complete...`);
    
    // Wait for a fixed amount of time to allow for any async operations
    await new Promise(resolve => setTimeout(resolve, WAIT_TIME_MS));

    // Output the captured logs as JSON
    console.log('\\n=== CAPTURED CONSOLE LOGS ===');
    console.log(JSON.stringify(capturedLogs, null, 2));
    console.log('=== END LOGS ===\\n');

  } catch (error) {
    console.error(`Error during browser automation: ${error.message}`);
    process.exit(1);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

captureConsoleLogs();