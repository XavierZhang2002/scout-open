#!/usr/bin/env node

import { run } from "./index";
import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { cleanupPidFile } from "./utils/processCheck";

// Set environment variable to indicate foreground mode
process.env.FOREGROUND_MODE = "true";

// Process command line arguments
const args = process.argv.slice(2);
const isDevMode = args.includes("--dev") || args.includes("-d");
const isVerboseMode = args.includes("--verbose") || args.includes("-v");

// Remove custom arguments, pass remaining arguments to the run function
const filteredArgs = args.filter(arg => !["--dev", "-d", "--verbose", "-v"].includes(arg));

// If there are other arguments, parse them
const options: any = {};
if (filteredArgs.length > 0) {
  // Parse port argument, e.g. --port 3000
  const portIndex = filteredArgs.indexOf("--port");
  if (portIndex !== -1 && filteredArgs[portIndex + 1]) {
    options.port = parseInt(filteredArgs[portIndex + 1]);
  }
}

console.log("🚀 Starting Claude Code Router in foreground mode...");
console.log("📝 Logs will be displayed in terminal");
console.log("⏹️  Press Ctrl+C to stop the server");
console.log("");

// Special handling for foreground mode
async function runForeground() {
  try {
    // Set up SIGINT and SIGTERM handlers to ensure graceful shutdown
    let isShuttingDown = false;

    const gracefulShutdown = (signal: string) => {
      if (isShuttingDown) {
        console.log(`\nForcefully shutting down due to ${signal}...`);
        process.exit(1);
      }

      isShuttingDown = true;
      console.log(`\n🛑 Received ${signal}, shutting down gracefully...`);

      // Clean up PID file
      cleanupPidFile();

      // Allow some time to complete current requests
      setTimeout(() => {
        console.log("✅ Server stopped successfully");
        process.exit(0);
      }, 2000);
    };

    process.on("SIGINT", () => gracefulShutdown("SIGINT"));
    process.on("SIGTERM", () => gracefulShutdown("SIGTERM"));

    // Call the original run function
    await run(options);

    console.log("✅ Server started successfully in foreground mode");
    console.log(`🌐 Server is running and accepting connections`);

    // Keep the process running
    process.stdin.resume();

  } catch (error: any) {
    console.error("❌ Failed to start server:", error.message);
    if (isVerboseMode) {
      console.error(error.stack);
    }
    process.exit(1);
  }
}

// Start foreground mode
runForeground();