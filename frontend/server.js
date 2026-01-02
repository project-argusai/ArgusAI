/* eslint-disable @typescript-eslint/no-require-imports */
/**
 * Custom HTTPS server for Next.js production
 *
 * This server enables HTTPS for the Next.js frontend using the same
 * SSL certificates configured for the backend. It also handles WebSocket
 * proxying for live camera streams (Story P16-2).
 *
 * IMPORTANT: WebSocket upgrade handler is set up BEFORE calling app.prepare()
 * to ensure our handler runs before Next.js's internal WebSocket handler.
 * This prevents duplicate 101 responses.
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

// Create HTTPS server
const server = createServer(httpsOptions, async (req, res) => {
  try {
    const parsedUrl = parse(req.url, true);
    await handle(req, res, parsedUrl);
  } catch (err) {
    console.error('Error occurred handling', req.url, err);
    res.statusCode = 500;
    res.end('Internal Server Error');
  }
});

// Check if a path should be proxied to our backend WebSocket
function isProxiedWebSocketPath(pathname) {
  return (pathname.startsWith('/api/v1/cameras/') && pathname.endsWith('/stream')) ||
    pathname === '/ws' || pathname.startsWith('/ws/');
}

// Set up our WebSocket upgrade handler BEFORE app.prepare()
// This ensures our handler is registered before Next.js adds its own
server.on('upgrade', (req, socket, head) => {
  const { pathname } = parse(req.url, true);

  // Only handle paths we want to proxy
  if (!isProxiedWebSocketPath(pathname)) {
    // Let other upgrade handlers (including Next.js) handle this
    return;
  }

  console.log(`WebSocket upgrade: ${pathname} -> ${backendHost}:${backendPort} (type: ${typeof backendPort})`);

  // CRITICAL: Block socket writes IMMEDIATELY to prevent Next.js from
  // sending its 101 response before our backend connection completes.
  // Next.js's upgrade handler runs synchronously after ours returns,
  // so we MUST block writes before returning from our handler.
  const originalWrite = socket.write.bind(socket);
  const originalEnd = socket.end.bind(socket);
  let writesBlocked = true;
  const pendingWrites = [];

  socket.write = function(...args) {
    if (!writesBlocked) {
      return originalWrite(...args);
    }
    // Queue the write for later
    pendingWrites.push({ method: 'write', args });
    return true;
  };

  socket.end = function(...args) {
    if (!writesBlocked) {
      return originalEnd(...args);
    }
    pendingWrites.push({ method: 'end', args });
    return true;
  };

  // Create raw TCP connection to backend
  console.log(`Connecting to backend ${backendHost}:${backendPort}...`);
  const backendSocket = net.connect(backendPort, backendHost, () => {
    console.log(`Backend connection established`);
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

    // Log the HTTP request for debugging
    console.log('HTTP request being sent:');
    console.log(httpRequest.replace(/\r\n/g, '\\r\\n\n'));

    // Send the upgrade request to backend
    backendSocket.write(httpRequest);

    // Also send any buffered data from client
    if (head.length > 0) {
      backendSocket.write(head);
    }

    // Restore socket methods and discard any pending writes from Next.js
    writesBlocked = false;
    socket.write = originalWrite;
    socket.end = originalEnd;

    // Log if Next.js tried to write (for debugging)
    if (pendingWrites.length > 0) {
      console.log(`Discarded ${pendingWrites.length} queued writes from Next.js`);
    }

    // Log data flow for debugging
    let backendDataCount = 0;
    let clientDataCount = 0;

    backendSocket.on('data', (data) => {
      backendDataCount++;
      if (backendDataCount <= 3) {
        console.log(`Backend -> Client [${backendDataCount}]: ${data.length} bytes`);
        if (backendDataCount === 1) {
          console.log('First response:', data.toString().substring(0, 200));
        }
      }
    });

    socket.on('data', (data) => {
      clientDataCount++;
      if (clientDataCount <= 3) {
        console.log(`Client -> Backend [${clientDataCount}]: ${data.length} bytes`);
      }
    });

    // Pipe data between sockets bidirectionally
    backendSocket.pipe(socket);
    socket.pipe(backendSocket);

    console.log('Pipe established, socket writable:', socket.writable, 'backendSocket writable:', backendSocket.writable);
  });

  // Handle cleanup
  socket.on('close', () => backendSocket.destroy());
  backendSocket.on('close', () => socket.destroy());
  socket.on('error', () => backendSocket.destroy());
  backendSocket.on('error', (err) => {
    console.error(`WebSocket proxy error: ${err.message} (code: ${err.code})`);
    socket.destroy();
  });

  // Log connection timeout
  backendSocket.setTimeout(5000, () => {
    console.error('Backend connection timeout');
    backendSocket.destroy();
  });
});

// Now prepare Next.js and start the server
app.prepare().then(() => {
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
