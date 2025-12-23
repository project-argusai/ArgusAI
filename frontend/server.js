/* eslint-disable @typescript-eslint/no-require-imports */
/**
 * Custom HTTPS server for Next.js production
 *
 * This server enables HTTPS for the Next.js frontend using the same
 * SSL certificates configured for the backend.
 *
 * Usage:
 *   SSL_CERT_FILE=/path/to/cert.pem SSL_KEY_FILE=/path/to/key.pem node server.js
 *
 * Environment variables:
 *   SSL_CERT_FILE - Path to SSL certificate file (required)
 *   SSL_KEY_FILE  - Path to SSL private key file (required)
 *   PORT          - Port to listen on (default: 3000)
 *   HOSTNAME      - Hostname to bind to (default: 0.0.0.0)
 */

const { createServer } = require('https');
const { parse } = require('url');
const next = require('next');
const fs = require('fs');

const dev = process.env.NODE_ENV !== 'production';
const hostname = process.env.HOSTNAME || '0.0.0.0';
const port = parseInt(process.env.PORT || '3000', 10);

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

// Initialize Next.js app
const app = next({ dev, hostname, port });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  createServer(httpsOptions, async (req, res) => {
    try {
      const parsedUrl = parse(req.url, true);
      await handle(req, res, parsedUrl);
    } catch (err) {
      console.error('Error occurred handling', req.url, err);
      res.statusCode = 500;
      res.end('Internal Server Error');
    }
  })
    .once('error', (err) => {
      console.error('Server error:', err);
      process.exit(1);
    })
    .listen(port, hostname, () => {
      console.log(`> Ready on https://${hostname}:${port}`);
      console.log(`> SSL Certificate: ${certFile}`);
    });
});
