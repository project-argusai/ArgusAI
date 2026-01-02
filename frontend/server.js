/* eslint-disable @typescript-eslint/no-require-imports */
/**
 * Custom HTTPS server for Next.js production
 *
 * This server enables HTTPS for the Next.js frontend using the same
 * SSL certificates configured for the backend. It also handles WebSocket
 * proxying for live camera streams (Story P16-2).
 *
 * Usage:
 *   SSL_CERT_FILE=/path/to/cert.pem SSL_KEY_FILE=/path/to/key.pem node server.js
 *
 * Environment variables:
 *   SSL_CERT_FILE - Path to SSL certificate file (required)
 *   SSL_KEY_FILE  - Path to SSL private key file (required)
 *   PORT          - Port to listen on (default: 3000)
 *   HOSTNAME      - Hostname to bind to (default: 0.0.0.0)
 *   BACKEND_URL   - Backend URL for API/WebSocket proxying (default: http://localhost:8000)
 */

const { createServer } = require('https');
const { parse } = require('url');
const next = require('next');
const fs = require('fs');
const net = require('net');

const dev = process.env.NODE_ENV !== 'production';
const hostname = process.env.HOSTNAME || '0.0.0.0';
const port = parseInt(process.env.PORT || '3000', 10);

// Backend URL for WebSocket proxying
const backendUrl = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// SSL certificate paths from environment variables
const certFile = process.env.SSL_CERT_FILE;
const keyFile = process.env.SSL_KEY_FILE;

// Validate SSL configuration
if (!certFile || !keyFile) {
  console.error('Error: SSL_CERT_FILE and SSL_KEY_FILE environment variables are required');
  console.error('Usage: SSL_CERT_FILE=/path/to/cert.pem SSL_KEY_FILE=/path/to/key.pem node server.js');
  process.exit(1);
}

// Check if certificate files exist
if (!fs.existsSync(certFile)) {
  console.error(`Error: Certificate file not found: ${certFile}`);
  process.exit(1);
}

if (!fs.existsSync(keyFile)) {
  console.error(`Error: Key file not found: ${keyFile}`);
  process.exit(1);
}

// Read SSL certificates
const httpsOptions = {
  cert: fs.readFileSync(certFile),
  key: fs.readFileSync(keyFile),
};

// Parse backend URL for WebSocket proxying
const backendUrlParsed = new URL(backendUrl);
const backendHost = backendUrlParsed.hostname;
const backendPort = backendUrlParsed.port || (backendUrlParsed.protocol === 'https:' ? 443 : 80);

// Initialize Next.js app
const app = next({ dev, hostname, port });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  const server = createServer(httpsOptions, async (req, res) => {
    const { pathname } = parse(req.url, true);

    // Check if this is a WebSocket upgrade request
    const isWebSocketUpgrade = req.headers.upgrade &&
      req.headers.upgrade.toLowerCase() === 'websocket';

    // Check if this path should be handled by our WebSocket proxy
    const isProxiedWebSocket = isWebSocketUpgrade && (
      (pathname.startsWith('/api/v1/cameras/') && pathname.endsWith('/stream')) ||
      pathname === '/ws' || pathname.startsWith('/ws/')
    );

    // For WebSocket proxy paths, don't let Next.js see the request at all
    // The 'upgrade' event will handle it
    if (isProxiedWebSocket) {
      console.log(`HTTP: Skipping WebSocket path ${pathname}`);
      // Don't respond - let the upgrade event handle it
      // The socket will be handled by server.on('upgrade', ...)
      return;
    }

    // Log API requests
    if (pathname.startsWith('/api/')) {
      console.log(`HTTP: Handling ${req.method} ${pathname}`);
    }

    try {
      await handle(req, res, parse(req.url, true));
    } catch (err) {
      console.error('Error occurred handling', req.url, err);
      res.statusCode = 500;
      res.end('Internal Server Error');
    }
  });

  // Handle WebSocket upgrade requests for streaming endpoints (Story P16-2)
  // Uses raw socket connection to backend for proper byte-level proxying
  server.on('upgrade', (req, socket, head) => {
    const { pathname } = parse(req.url, true);

    // Proxy WebSocket connections for camera streams and other WS endpoints
    if ((pathname.startsWith('/api/v1/cameras/') && pathname.endsWith('/stream')) ||
        pathname === '/ws' || pathname.startsWith('/ws/')) {
      console.log(`WebSocket upgrade: ${pathname} -> ${backendHost}:${backendPort}`);

      // Create raw TCP connection to backend
      const backendSocket = net.connect(backendPort, backendHost, () => {
        // Build the HTTP upgrade request to send to backend
        // Filter out compression headers to avoid frame issues
        let httpRequest = `${req.method} ${req.url} HTTP/1.1\r\n`;
        for (const [key, value] of Object.entries(req.headers)) {
          // Skip compression extensions and update host
          if (key.toLowerCase() === 'sec-websocket-extensions') continue;
          if (key.toLowerCase() === 'host') {
            httpRequest += `Host: ${backendHost}:${backendPort}\r\n`;
          } else {
            httpRequest += `${key}: ${value}\r\n`;
          }
        }
        httpRequest += '\r\n';

        console.log(`WebSocket proxy: sending ${httpRequest.length} bytes HTTP request`);

        // Send the upgrade request to backend
        backendSocket.write(httpRequest);

        // Also send any buffered data from client
        if (head.length > 0) {
          console.log(`WebSocket proxy: sending ${head.length} bytes head data`);
          backendSocket.write(head);
        }

        // Debug: log first few chunks from both directions
        let backendChunks = 0;
        let clientChunks = 0;

        const backendHandler = (chunk) => {
          backendChunks++;
          if (backendChunks <= 3) {
            console.log(`WS BACKEND->CLIENT #${backendChunks}: ${chunk.length} bytes, hex: ${chunk.slice(0, Math.min(20, chunk.length)).toString('hex')}`);
          }
        };
        backendSocket.on('data', backendHandler);

        const clientHandler = (chunk) => {
          clientChunks++;
          if (clientChunks <= 3) {
            console.log(`WS CLIENT->BACKEND #${clientChunks}: ${chunk.length} bytes, hex: ${chunk.slice(0, Math.min(20, chunk.length)).toString('hex')}`);
          }
        };
        socket.on('data', clientHandler);

        // Pipe data between sockets bidirectionally
        backendSocket.pipe(socket);
        socket.pipe(backendSocket);
      });

      // Handle cleanup
      socket.on('close', () => backendSocket.destroy());
      backendSocket.on('close', () => socket.destroy());
      socket.on('error', () => backendSocket.destroy());
      backendSocket.on('error', (err) => {
        console.error('WebSocket proxy error:', err.message);
        socket.destroy();
      });
    } else {
      // Let Next.js handle other WebSocket connections (e.g., HMR in dev mode)
      socket.destroy();
    }
  });

  server
    .once('error', (err) => {
      console.error('Server error:', err);
      process.exit(1);
    })
    .listen(port, hostname, () => {
      console.log(`> Ready on https://${hostname}:${port}`);
      console.log(`> SSL Certificate: ${certFile}`);
      console.log(`> Backend WebSocket proxy: ${backendUrl}`);
    });
});
