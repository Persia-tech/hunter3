import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

const allowedHost = process.env.VITE_ALLOWED_HOST ?? process.env.RAILWAY_PUBLIC_DOMAIN;
const allowedHosts = allowedHost ? [allowedHost] : [];

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    allowedHosts,
    proxy: { '/api': 'http://localhost:8000' },
  },
  preview: {
    host: '0.0.0.0',
    allowedHosts,
  },
  test: { environment: 'jsdom' },
});
