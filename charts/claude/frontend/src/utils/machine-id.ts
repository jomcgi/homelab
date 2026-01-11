import os from 'os';
import crypto from 'crypto';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

/**
 * Get the primary network interface MAC address
 * On macOS, this is typically en0
 * On Linux, this is typically eth0, eno1, or enp0s*
 */
async function getPrimaryMacAddress(): Promise<string> {
  try {
    // Platform-specific commands to get MAC address
    let command: string;
    const platform = os.platform();
    
    if (platform === 'darwin') {
      // macOS: Get en0 MAC address (primary network interface)
      command = 'ifconfig en0 | grep ether | awk \'{print $2}\'';
    } else if (platform === 'linux') {
      // Linux: Try common interface names
      command = 'ip link show | grep -E "eno1|eth0|enp0s[0-9]+" -A1 | grep link/ether | head -1 | awk \'{print $2}\'';
    } else if (platform === 'win32') {
      // Windows: Get first physical adapter MAC
      command = 'wmic nic where "PhysicalAdapter=TRUE" get MACAddress | findstr /r "[0-9A-F][0-9A-F]:[0-9A-F][0-9A-F]" | head -1';
    } else {
      throw new Error(`Unsupported platform: ${platform}`);
    }
    
    const { stdout } = await execAsync(command);
    const mac = stdout.trim();
    
    if (!mac) {
      throw new Error('No MAC address found');
    }
    
    return mac;
  } catch (_error) {
    // Fallback: Use os.networkInterfaces()
    const interfaces = os.networkInterfaces();
    for (const name of Object.keys(interfaces)) {
      const iface = interfaces[name];
      if (!iface) continue;
      
      for (const info of iface) {
        // Skip internal (loopback) interfaces
        if (!info.internal && info.mac && info.mac !== '00:00:00:00:00:00') {
          return info.mac;
        }
      }
    }
    
    throw new Error('Unable to determine MAC address');
  }
}

/**
 * Generate a machine ID based on hostname and MAC address
 * Format: {hostname}-{16char_hash}
 * Example: "wenbomacbook-a1b2c3d4e5f6g7h8"
 */
export async function generateMachineId(): Promise<string> {
  // Get hostname (lowercase) and sanitize it
  // Remove dots and other special characters, keeping only alphanumeric and hyphens
  const hostname = os.hostname()
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '');
  
  // Get MAC address
  const macAddress = await getPrimaryMacAddress();
  
  // Generate SHA256 hash of MAC address
  const hash = crypto
    .createHash('sha256')
    .update(macAddress.toLowerCase())
    .digest('hex')
    .substring(0, 16); // Take first 16 characters
  
  return `${hostname}-${hash}`;
}