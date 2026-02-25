#!/bin/bash
# ══════════════════════════════════════════════════════════════
#  AutoCO Lynix Bot — One-Click VPS Setup (Ubuntu/Debian)
#  Usage: chmod +x setup.sh && sudo ./setup.sh
# ══════════════════════════════════════════════════════════════

set -e

# ─── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════╗"
echo "║    AutoCO Lynix Bot — VPS Setup          ║"
echo "╚══════════════════════════════════════════╝"
echo -e "${NC}"

# ─── Check root ──────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[!] Please run as root: sudo ./setup.sh${NC}"
    exit 1
fi

# ─── Config ──────────────────────────────────────────────────
BOT_DIR="/opt/autoco-lynix"
SERVICE_NAME="autoco-bot"
VENV_DIR="$BOT_DIR/venv"

# ─── Prompt for .env values ─────────────────────────────────
echo -e "${YELLOW}[?] Bot Configuration${NC}"
read -p "    Telegram Bot Token: " BOT_TOKEN
read -p "    Admin Telegram ID: " ADMIN_ID
read -p "    Logs Group/Channel ID (e.g. -1003642791388): " LOGS_ID
read -p "    Antispam Free (seconds, default 60): " ANTISPAM_FREE
read -p "    Antispam Paid (seconds, default 30): " ANTISPAM_PAID

ANTISPAM_FREE=${ANTISPAM_FREE:-60}
ANTISPAM_PAID=${ANTISPAM_PAID:-30}

if [ -z "$BOT_TOKEN" ] || [ -z "$ADMIN_ID" ]; then
    echo -e "${RED}[!] Bot Token and Admin ID are required!${NC}"
    exit 1
fi

# ─── Step 1: System packages ────────────────────────────────
echo -e "\n${GREEN}[1/6] Installing system dependencies...${NC}"
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git curl > /dev/null 2>&1
echo -e "${GREEN}      ✓ System packages installed${NC}"

# ─── Step 2: Copy bot files ─────────────────────────────────
echo -e "${GREEN}[2/6] Setting up bot directory...${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$SCRIPT_DIR/AutoshBotSRC"

# Check if source exists (script is in repo root)
if [ ! -d "$SRC_DIR" ]; then
    # Maybe script is inside AutoshBotSRC
    SRC_DIR="$SCRIPT_DIR"
    if [ ! -f "$SRC_DIR/bot.py" ]; then
        echo -e "${RED}[!] Cannot find bot.py! Run this script from the project root or AutoshBotSRC directory.${NC}"
        exit 1
    fi
fi

mkdir -p "$BOT_DIR"
cp -r "$SRC_DIR"/* "$BOT_DIR/"
echo -e "${GREEN}      ✓ Bot files copied to $BOT_DIR${NC}"

# ─── Step 3: Create .env ────────────────────────────────────
echo -e "${GREEN}[3/6] Creating .env config...${NC}"
cat > "$BOT_DIR/.env" <<EOF
TOKEN=$BOT_TOKEN
ADMIN_ID=$ADMIN_ID
ANTISPAM_TIME_FREE=$ANTISPAM_FREE
ANTISPAM_TIME_PAID=$ANTISPAM_PAID
LOGS=$LOGS_ID
EOF
echo -e "${GREEN}      ✓ .env created${NC}"

# ─── Step 4: Python venv + deps ─────────────────────────────
echo -e "${GREEN}[4/6] Setting up Python virtual environment...${NC}"
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -r "$BOT_DIR/requirements.txt" -q
deactivate
echo -e "${GREEN}      ✓ Python dependencies installed${NC}"

# ─── Step 5: Create systemd service ─────────────────────────
echo -e "${GREEN}[5/6] Creating systemd service...${NC}"
cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=AutoCO Lynix Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$BOT_DIR
EnvironmentFile=$BOT_DIR/.env
ExecStart=$VENV_DIR/bin/python3 bot.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl start ${SERVICE_NAME}
echo -e "${GREEN}      ✓ Service created and started${NC}"

# ─── Step 6: Verify ─────────────────────────────────────────
echo -e "${GREEN}[6/6] Verifying...${NC}"
sleep 3

if systemctl is-active --quiet ${SERVICE_NAME}; then
    echo -e "${GREEN}      ✓ Bot is running!${NC}"
else
    echo -e "${RED}      ✗ Bot failed to start. Check logs:${NC}"
    echo -e "${YELLOW}        journalctl -u ${SERVICE_NAME} -n 30${NC}"
fi

# ─── Done ────────────────────────────────────────────────────
echo -e "\n${CYAN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${CYAN}══════════════════════════════════════════${NC}"
echo ""
echo -e "  ${YELLOW}Useful commands:${NC}"
echo -e "    Status:  ${CYAN}systemctl status ${SERVICE_NAME}${NC}"
echo -e "    Logs:    ${CYAN}journalctl -u ${SERVICE_NAME} -f${NC}"
echo -e "    Stop:    ${CYAN}systemctl stop ${SERVICE_NAME}${NC}"
echo -e "    Restart: ${CYAN}systemctl restart ${SERVICE_NAME}${NC}"
echo -e "    Config:  ${CYAN}nano $BOT_DIR/.env${NC}"
echo ""
