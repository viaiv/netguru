import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function extractBackendPort(backendEnvFile: string): string | null {
  if (!fs.existsSync(backendEnvFile)) {
    return null;
  }

  const envText = fs.readFileSync(backendEnvFile, 'utf-8');
  const portMatch = envText.match(/^UVICORN_PORT\s*=\s*["']?([^"'#\s]+)["']?/m);
  if (!portMatch) {
    return null;
  }

  const port = portMatch[1];
  return /^\d+$/.test(port) ? port : null;
}

function resolveDevApiUrl(mode: string): string | null {
  const env = loadEnv(mode, process.cwd(), '');
  if (env.VITE_API_URL?.trim()) {
    return env.VITE_API_URL.trim();
  }

  const backendEnvFile = env.DEV_BACKEND_ENV_FILE?.trim()
    ? path.resolve(__dirname, env.DEV_BACKEND_ENV_FILE.trim())
    : path.resolve(__dirname, '../backend/.env');

  const backendPort = extractBackendPort(backendEnvFile);
  if (!backendPort) {
    return null;
  }

  return `http://localhost:${backendPort}`;
}

export default defineConfig(({ command, mode }) => {
  if (command === 'serve') {
    const devApiUrl = resolveDevApiUrl(mode);
    if (devApiUrl) {
      process.env.VITE_API_URL = devApiUrl;
    }
  }

  return {
    plugins: [react()],
    server: {
      host: '0.0.0.0',
      port: 5173,
    },
  };
});
