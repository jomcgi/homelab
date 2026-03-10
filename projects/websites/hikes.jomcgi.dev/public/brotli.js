// Robust Brotli decompression using locally-hosted brotli-wasm
// Based on research recommendations for performance vs bundle size balance

let brotliModule = null;

// Initialize the WASM module on first load
async function initBrotli() {
  if (brotliModule) {
    return brotliModule;
  }

  try {
    // Import the locally-hosted brotli-wasm module
    const module = await import("./brotli-wasm.js");
    brotliModule = await module.default;
    console.log("✅ Brotli WASM module loaded successfully");
    return brotliModule;
  } catch (error) {
    const errorMsg = `CRITICAL ERROR: Failed to load Brotli WASM module. This application requires Brotli decompression to function. Error: ${error.message}`;
    console.error(errorMsg);
    throw new Error(errorMsg);
  }
}

// Global decompression function
window.BrotliDecompress = async function (arrayBuffer) {
  try {
    // Ensure WASM module is loaded
    const brotli = await initBrotli();

    if (!brotli || !brotli.decompress) {
      throw new Error(
        "CRITICAL ERROR: Brotli decompression function not available. The WASM module failed to initialize properly.",
      );
    }

    // Convert ArrayBuffer to Uint8Array
    const compressedData = new Uint8Array(arrayBuffer);

    // Decompress using brotli-wasm
    const decompressedData = brotli.decompress(compressedData);

    // Convert decompressed Uint8Array to string
    const decompressedString = new TextDecoder("utf-8").decode(
      decompressedData,
    );

    console.log(
      `✅ Successfully decompressed ${compressedData.length} bytes to ${decompressedString.length} characters`,
    );

    return decompressedString;
  } catch (error) {
    const errorMsg = `FATAL: Brotli decompression failed and the application cannot continue. This is a critical system error. Details: ${error.message}`;
    console.error(errorMsg);
    throw new Error(errorMsg);
  }
};

// Pre-load the WASM module on script load for faster decompression
initBrotli().catch((error) => {
  console.error(
    "WARNING: Failed to pre-load Brotli WASM module:",
    error.message,
  );
  console.error(
    "The application will attempt to load it when needed, but may fail.",
  );
});
