#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# SAM VPS Setup Script
# Run on a fresh Ubuntu 22.04 VPS (Hetzner / DigitalOcean / any provider)
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/yashhgill/sam/main/deploy/setup-vps.sh | bash
#   OR
#   bash deploy/setup-vps.sh
#
# After running, set your .env variables, then:
#   cd /opt/sam && docker compose up -d
# ─────────────────────────────────────────────────────────────────────────────
set -e

REPO="https://github.com/yashhgill/sam.git"
APP_DIR="/opt/sam"
DOMAIN="sam-api.harnova.my"

echo "════════════════════════════════════════"
echo "  SAM VPS Setup"
echo "════════════════════════════════════════"

# ── 1. System packages ─────────────────────────────────────────────────────
echo "→ Updating system..."
apt-get update -q
apt-get install -y -q curl git nginx certbot python3-certbot-nginx ufw

# ── 2. Docker ──────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "→ Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
fi

# ── 3. Clone repo ──────────────────────────────────────────────────────────
echo "→ Cloning SAM repo..."
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR" && git pull
else
    git clone "$REPO" "$APP_DIR"
fi

# ── 4. Create .env ─────────────────────────────────────────────────────────
if [ ! -f "$APP_DIR/.env" ]; then
    echo "→ Creating .env file..."
    cat > "$APP_DIR/.env" << 'ENV'
# ─── SAM Production .env ─────────────────────────────────────────────────
# Fill in your actual keys before starting SAM

GROQ_API_KEY=your_groq_key_here
OMNIROUTE_API_KEY=your_omniroute_key_here
OMNIROUTE_URL=http://localhost:20128/v1

# Supabase (optional — SQLite used as fallback)
SUPABASE_URL=https://whmaeqcvsmpwqwrmurm.supabase.co
SUPABASE_SERVICE_KEY=your_service_key_here
SUPABASE_ANON_KEY=your_anon_key_here

# Models (these work out of the box with Groq)
MODEL_FAST=llama-3.1-8b-instant
MODEL_SMART=llama-3.3-70b-versatile
MODEL_REASON=deepseek-r1-distill-llama-70b

DEBUG=false
ENV
    echo ""
    echo "⚠️  IMPORTANT: Edit $APP_DIR/.env and add your GROQ_API_KEY before continuing!"
    echo "   Run: nano $APP_DIR/.env"
    echo ""
fi

# ── 5. Nginx config ────────────────────────────────────────────────────────
echo "→ Configuring Nginx..."
cat > "/etc/nginx/sites-available/sam-api" << NGINX
server {
    listen 80;
    server_name ${DOMAIN};

    # SAM backend API + SSE
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        # SSE support — critical for streaming
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        chunked_transfer_encoding on;

        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;

        # CORS — Cloudflare Pages handles this via origin
        add_header Access-Control-Allow-Origin "*" always;
        add_header Access-Control-Allow-Methods "GET, POST, DELETE, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Content-Type, Authorization" always;

        if (\$request_method = 'OPTIONS') {
            return 204;
        }
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400s;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/sam-api /etc/nginx/sites-enabled/sam-api
nginx -t && systemctl reload nginx

# ── 6. UFW firewall ────────────────────────────────────────────────────────
echo "→ Configuring firewall..."
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ── 7. SSL with Let's Encrypt ──────────────────────────────────────────────
echo ""
echo "→ Setting up SSL for ${DOMAIN}..."
echo "  Make sure your DNS A record points ${DOMAIN} to this server's IP first!"
echo ""
read -p "  Press Enter when DNS is ready, or Ctrl+C to skip SSL setup..."
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email admin@harnova.my || {
    echo "⚠️  SSL setup failed. You can run it manually: certbot --nginx -d ${DOMAIN}"
}

# ── 8. Start SAM ──────────────────────────────────────────────────────────
echo "→ Starting SAM..."
cd "$APP_DIR"
docker compose up -d --build

echo ""
echo "════════════════════════════════════════"
echo "  ✅ SAM is running!"
echo ""
echo "  API:    https://${DOMAIN}"
echo "  Health: https://${DOMAIN}/health"
echo ""
echo "  Logs:   docker compose logs -f   (from $APP_DIR)"
echo "  Stop:   docker compose down"
echo "  Update: git pull && docker compose up -d --build"
echo "════════════════════════════════════════"
