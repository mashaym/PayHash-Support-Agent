import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Stay on the exact port already allowed by the backend's CORS configuration.
  server: { host: '127.0.0.1', port: 5173, strictPort: true },
});
