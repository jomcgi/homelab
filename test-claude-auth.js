#!/usr/bin/env node

/**
 * Test script to verify claude /login can be spawned as a subprocess
 * and accepts stdin for the auth code.
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const HOME = process.env.HOME || '/home/user';
const CLAUDE_BIN = path.join(HOME, '.npm-global', 'bin', 'claude');

console.log('Testing Claude CLI authentication flow...\n');
console.log(`HOME: ${HOME}`);
console.log(`CLAUDE_BIN: ${CLAUDE_BIN}`);
console.log(`Binary exists: ${fs.existsSync(CLAUDE_BIN)}\n`);

// Test 1: Check if /login works as an argument
console.log('Test 1: Spawning claude /login...');
const authProcess = spawn(CLAUDE_BIN, ['/login'], {
  cwd: HOME,
  env: { ...process.env, HOME },
  stdio: ['pipe', 'pipe', 'pipe'],
});

let output = '';
let hasUrl = false;

authProcess.stdout.on('data', (data) => {
  const str = data.toString();
  output += str;
  console.log('[STDOUT]', str);

  // Check for auth URL
  const urlMatch = str.match(/https:\/\/[^\s]+/);
  if (urlMatch) {
    console.log('\n✓ Found auth URL:', urlMatch[0]);
    hasUrl = true;
  }
});

authProcess.stderr.on('data', (data) => {
  const str = data.toString();
  output += str;
  console.log('[STDERR]', str);

  // Check for auth URL in stderr too
  const urlMatch = str.match(/https:\/\/[^\s]+/);
  if (urlMatch) {
    console.log('\n✓ Found auth URL in stderr:', urlMatch[0]);
    hasUrl = true;
  }
});

authProcess.on('error', (err) => {
  console.error('\n✗ Process error:', err.message);
  process.exit(1);
});

authProcess.on('close', (code) => {
  console.log(`\n✓ Process exited with code: ${code}`);
  console.log(`✓ Found URL: ${hasUrl}`);

  // Test 2: Check auth file location
  const authFile = path.join(HOME, '.claude', 'auth.json');
  console.log(`\nTest 2: Checking auth file location...`);
  console.log(`Auth file path: ${authFile}`);
  console.log(`Auth file exists: ${fs.existsSync(authFile)}`);

  if (fs.existsSync(authFile)) {
    console.log('Auth file contents:', fs.readFileSync(authFile, 'utf-8').substring(0, 100));
  }

  // Summary
  console.log('\n=== Summary ===');
  console.log(`/login as argument works: ${code === 0 || hasUrl ? 'YES' : 'NO'}`);
  console.log(`Auth URL found in output: ${hasUrl ? 'YES' : 'NO'}`);
  console.log(`Auth file location correct: ${fs.existsSync(authFile) ? 'YES' : 'UNKNOWN'}`);

  // Kill the process if still running
  authProcess.kill();
  process.exit(0);
});

// Give it 5 seconds then kill
setTimeout(() => {
  console.log('\n⏱ Timeout reached, killing process...');
  authProcess.kill();
}, 5000);
