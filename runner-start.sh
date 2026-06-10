#!/bin/sh
set -e

# Wait for n8n broker to be ready
echo "Waiting for n8n broker at n8n-media-server:5679..."
until node -e "
  const http = require('http');
  http.get('http://n8n-media-server:5679/healthz', res => {
    process.exit(res.statusCode === 200 ? 0 : 1);
  }).on('error', () => process.exit(1));
" 2>/dev/null; do
  sleep 2
done
echo "n8n broker ready"

# Exchange auth token for a short-lived grant token
GRANT_TOKEN=$(node -e "
  const http = require('http');
  const body = JSON.stringify({ token: process.env.N8N_RUNNERS_AUTH_TOKEN });
  const req = http.request({
    hostname: 'n8n-media-server', port: 5679,
    path: '/runners/auth', method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }
  }, res => {
    let d = '';
    res.on('data', c => d += c);
    res.on('end', () => {
      try { const r = JSON.parse(d); process.stdout.write((r.data && r.data.token) || r.token || ''); }
      catch(e) { process.stderr.write('parse error: ' + d); process.exit(1); }
    });
  });
  req.on('error', e => { process.stderr.write(e.message); process.exit(1); });
  req.write(body); req.end();
")

if [ -z "$GRANT_TOKEN" ]; then
  echo "ERROR: failed to obtain grant token from n8n broker"
  exit 1
fi

echo "Grant token obtained, starting task runner..."
export N8N_RUNNERS_GRANT_TOKEN="$GRANT_TOKEN"
exec node /usr/local/lib/node_modules/n8n/node_modules/@n8n/task-runner/dist/start.js
