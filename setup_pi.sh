#!/bin/bash

################################################################################
# DHCP Dashboard - Raspberry Pi Setup Script
# 
# This script performs complete installation and configuration of the DHCP
# Dashboard application with automatic startup on boot.
#
# Usage: sudo bash setup_pi.sh
################################################################################

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR"
APP_FILE="dhcp_dashboard.py"
SERVICE_NAME="dhcp-dashboard"

################################################################################
# Helper Functions
################################################################################

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

################################################################################
# Check Prerequisites
################################################################################

print_status "Starting DHCP Dashboard installation..."
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

print_success "Prerequisites check passed"
echo ""

################################################################################
# System Update and Upgrade
################################################################################

print_status "Updating package lists..."
apt-get update -qq

print_success "Package lists updated"
echo ""

print_status "Upgrading installed packages (this may take a few minutes)..."
apt-get upgrade -y

print_success "System packages upgraded"
echo ""

################################################################################
# Install Required Packages
################################################################################

print_status "Installing required packages (dnsmasq, hostapd)..."

# Install dnsmasq (DHCP/DNS server)
if ! dpkg -l | grep -q "^ii  dnsmasq "; then
    print_status "Installing dnsmasq..."
    apt-get install -y dnsmasq
    print_success "dnsmasq installed"
else
    print_success "dnsmasq already installed"
fi

# Install hostapd (Access Point software)
if ! dpkg -l | grep -q "^ii  hostapd "; then
    print_status "Installing hostapd..."
    apt-get install -y hostapd
    print_success "hostapd installed"
else
    print_success "hostapd already installed"
fi

# Install Python pip if not present
if ! command -v pip3 &> /dev/null; then
    print_status "Installing python3-pip..."
    apt-get install -y python3-pip
    print_success "pip3 installed"
fi

echo ""

################################################################################
# Install Python Dependencies
################################################################################

print_status "Installing Python dependencies from requirements.txt..."
cd "$APP_DIR"

if [ -f "requirements.txt" ]; then
    pip3 install -r requirements.txt --break-system-packages
    print_success "Python dependencies installed"
else
    print_warning "requirements.txt not found, installing Flask manually..."
    pip3 install flask --break-system-packages
fi

echo ""

################################################################################
# Configure File Permissions
################################################################################

print_status "Setting up file permissions..."

# Ensure the app file is executable (not really needed for Python, but good practice)
chmod +x "$APP_DIR/$APP_FILE" 2>/dev/null || true

# Create log files with proper permissions
touch "$APP_DIR/dhcp_dashboard.log"
touch "$APP_DIR/connection_log.json"
chmod 644 "$APP_DIR/dhcp_dashboard.log"
chmod 644 "$APP_DIR/connection_log.json"

# Allow the application to run on port 8080 without sudo (if needed)
# Note: Ports below 1024 require root, but 8080 doesn't

print_success "File permissions configured"
echo ""

################################################################################
# Stop Conflicting Services
################################################################################

print_status "Stopping services before configuration..."

# Stop hostapd and dnsmasq if they're running
systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true

print_success "Services stopped"
echo ""

################################################################################
# Create Systemd Service
################################################################################

print_status "Creating systemd service for auto-start on boot..."

# Create the systemd service file
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=DHCP Dashboard Web Application
After=network.target dnsmasq.service

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/python3 ${APP_DIR}/${APP_FILE}
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Environment
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF

print_success "Systemd service file created at /etc/systemd/system/${SERVICE_NAME}.service"
echo ""

################################################################################
# Enable and Start Service
################################################################################

print_status "Enabling ${SERVICE_NAME} service to start on boot..."

# Reload systemd to recognize new service
systemctl daemon-reload

# Enable the service (start on boot)
systemctl enable ${SERVICE_NAME}.service

print_success "Service enabled for automatic startup on boot"
echo ""

################################################################################
# Configure Sudoers (Allow Python Script to Run System Commands)
################################################################################

print_status "Configuring sudo permissions for the application..."

# Create a sudoers file that allows the application to run necessary commands without password
SUDOERS_FILE="/etc/sudoers.d/dhcp-dashboard"

cat > "$SUDOERS_FILE" << 'EOF'
# DHCP Dashboard - Allow necessary system commands without password
# This allows the Flask app to manage network services

# Allow all users to run systemctl commands for these services
ALL ALL=(ALL) NOPASSWD: /bin/systemctl restart dnsmasq
ALL ALL=(ALL) NOPASSWD: /bin/systemctl status dnsmasq
ALL ALL=(ALL) NOPASSWD: /bin/systemctl restart hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl status hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl is-active hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl is-enabled hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl stop hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl enable hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl disable hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl unmask hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl restart dhcpcd

# Allow network interface commands
ALL ALL=(ALL) NOPASSWD: /sbin/ifconfig wlan0 *
ALL ALL=(ALL) NOPASSWD: /sbin/wpa_cli *
ALL ALL=(ALL) NOPASSWD: /sbin/iw dev wlan0 *

# Allow iptables commands
ALL ALL=(ALL) NOPASSWD: /sbin/iptables *
ALL ALL=(ALL) NOPASSWD: /sbin/sysctl *

# Allow shutdown
ALL ALL=(ALL) NOPASSWD: /sbin/shutdown *
EOF

# Set proper permissions on sudoers file
chmod 0440 "$SUDOERS_FILE"

# Validate the sudoers file
if visudo -c -f "$SUDOERS_FILE"; then
    print_success "Sudo permissions configured"
else
    print_error "Sudoers file validation failed"
    rm "$SUDOERS_FILE"
    exit 1
fi

echo ""

################################################################################
# Start the Service
################################################################################

print_status "Starting ${SERVICE_NAME} service..."

# Start the service
systemctl start ${SERVICE_NAME}.service

# Wait a moment for service to start
sleep 3

# Check if service is running
if systemctl is-active --quiet ${SERVICE_NAME}.service; then
    print_success "Service started successfully!"
else
    print_error "Service failed to start. Check logs with: journalctl -u ${SERVICE_NAME}.service -n 50"
    exit 1
fi

echo ""

################################################################################
# Display Network Information
################################################################################

print_status "Getting network information..."

# Get the IP address of the Raspberry Pi
IP_ADDRESS=$(hostname -I | awk '{print $1}')

echo ""
print_success "=========================================="
print_success "INSTALLATION COMPLETED SUCCESSFULLY!"
print_success "=========================================="
echo ""
echo -e "${GREEN}Dashboard URL:${NC} http://${IP_ADDRESS}:8080"
echo -e "${GREEN}or:${NC} http://$(hostname).local:8080"
echo ""
echo -e "${YELLOW}Service Management Commands:${NC}"
echo -e "  Start:   ${BLUE}sudo systemctl start ${SERVICE_NAME}${NC}"
echo -e "  Stop:    ${BLUE}sudo systemctl stop ${SERVICE_NAME}${NC}"
echo -e "  Restart: ${BLUE}sudo systemctl restart ${SERVICE_NAME}${NC}"
echo -e "  Status:  ${BLUE}sudo systemctl status ${SERVICE_NAME}${NC}"
echo -e "  Logs:    ${BLUE}sudo journalctl -u ${SERVICE_NAME} -f${NC}"
echo ""
echo -e "${YELLOW}Configuration Files:${NC}"
echo -e "  App Directory:     ${APP_DIR}"
echo -e "  Application Log:   ${APP_DIR}/dhcp_dashboard.log"
echo -e "  Connection Log:    ${APP_DIR}/connection_log.json"
echo -e "  DNSMASQ Config:    /etc/dnsmasq.conf"
echo -e "  Hostapd Config:    /etc/hostapd/hostapd.conf"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "  1. Access the dashboard at: ${BLUE}http://${IP_ADDRESS}:8080${NC}"
echo -e "  2. Configure your Access Point (SSID, password)"
echo -e "  3. Start the Access Point from the dashboard"
echo -e "  4. Connect devices via Wi-Fi or Ethernet switch"
echo ""
print_success "The application will automatically start on every boot!"
echo ""

################################################################################
# Optional: Enable DHCP logging in dnsmasq
################################################################################

print_status "Note: DHCP logging will be enabled when you configure the Access Point"
print_status "through the web interface."
echo ""

print_success "Setup complete! Enjoy your DHCP Dashboard!"