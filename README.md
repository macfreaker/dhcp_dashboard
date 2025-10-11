<div align="center">

# 🚀 DHCP/DNS Dashboard for Raspberry Pi

### _Developed by **JPHsystems**_

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.x-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/flask-3.0-green.svg)](https://flask.palletsprojects.com/)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red.svg)](https://www.raspberrypi.org/)

**A comprehensive Flask web application for managing DHCP/DNS and Access Point functionality on Raspberry Pi**

[Features](#-features) • [Quick Start](#-quick-start) • [API Docs](#-interactive-api-documentation-swagger-ui) • [Installation](#-installation) • [Network Setup](#-network-configuration)

---

</div>

## 📋 Overview

Transform your Raspberry Pi into a powerful **network management hub** with:
- 📡 **Wireless Access Point** (wlan0) broadcasting your own Wi-Fi network
- 📶 **Wi-Fi Client** (wlan1 - USB adapter) for internet connectivity
- 🔌 **Ethernet connectivity** for wired devices via switch
- 🌐 **Unified local network** - all devices on same subnet (192.168.4.x)
- 📊 **Connection tracking** with detailed logging
- 🖥️ **Web dashboard** for easy management
- 📚 **Swagger API** for programmatic control

## ✨ Features

### 🖥️ Web Dashboard
- **DHCP Host Management**
  - Add new hosts with MAC addresses, hostnames, and optional static IP addresses
  - Edit existing host configurations
  - Remove hosts from the DHCP server
  - View all configured hosts in a responsive card-based layout

- **Access Point (AP) Mode** ⭐ NEW
  - Configure Raspberry Pi as a wireless access point
  - Broadcast your own Wi-Fi network (SSID & password configuration)
  - Create unified local network across Wi-Fi (wlan0) and Ethernet (eth0/switch)
  - All devices (wireless + wired) on same subnet (192.168.4.x)
  - Start/stop access point services
  - Monitor connected clients
  - Configure channel and country settings
  - Perfect for isolated lab/testing networks
  - **Connection logging** - Track all device connections/disconnections with timestamps
  - **Internet sharing toggle** - Enable/disable internet access from wlan1 to local network

- **DNSMASQ Service Control**
  - Restart the dnsmasq service
  - Check dnsmasq status
  - Create timestamped backups of the configuration file

- **Wi-Fi Client Configuration** 📶
  - Connect to existing Wi-Fi networks via **wlan1** (USB Wi-Fi adapter)
  - Update Wi-Fi SSID and password through the web interface
  - Automatically reconnect to new networks
  - **Note:** Requires USB Wi-Fi dongle as wlan1
  - wlan0 is reserved for Access Point mode

- **System Management** 🔧
  - Shutdown the Raspberry Pi remotely through the web interface
  - Includes confirmation screen for safety

---

### 📚 Interactive API Documentation (Swagger UI)

Access the **interactive Swagger UI** for complete API documentation and testing:

**Swagger URL:** `http://192.168.4.1:8080/api/docs`

Features:
- 📖 Complete API documentation with request/response examples
- 🧪 Interactive testing - try API calls directly from your browser
- 📋 Request/response schemas for all endpoints
- 🔍 Parameter descriptions and validation rules
- 🎯 Organized by namespaces (Hosts, Access Point, Connections, Logs)

### � RESTful API Endpoints

#### Host Management
- **List all hosts**
  ```bash
  curl http://your-ip:8080/api/hosts
  ```

- **Add a new host**
  ```bash
  curl -X POST -H "Content-Type: application/json" \
    -d '{"mac":"00:11:22:33:44:55","hostname":"newdevice","ip":"192.168.1.100"}' \
    http://your-ip:8080/api/hosts
  ```
  *Note: IP address is optional*

- **Remove a host**
  ```bash
  curl -X DELETE http://your-ip:8080/api/hosts/00:11:22:33:44:55
  ```

#### 📡 Access Point Management
- **Get AP configuration**
  ```bash
  curl http://your-ip:8080/api/ap/config
  ```

- **Configure access point**
  ```bash
  curl -X POST -H "Content-Type: application/json" \
    -d '{"ssid":"MyAP","password":"securepass123","channel":"6","country":"BE"}' \
    http://your-ip:8080/api/ap/config
  ```

- **Start access point**
  ```bash
  curl -X POST http://your-ip:8080/api/ap/start
  ```

- **Stop access point**
  ```bash
  curl -X POST http://your-ip:8080/api/ap/stop
  ```

- **Get AP status**
  ```bash
  curl http://your-ip:8080/api/ap/status
  ```

- **Get internet sharing status**
  ```bash
  curl http://your-ip:8080/api/ap/internet-sharing/status
  ```

- **Enable internet sharing**
  ```bash
  curl -X POST http://your-ip:8080/api/ap/internet-sharing/enable
  ```

- **Disable internet sharing**
  ```bash
  curl -X POST http://your-ip:8080/api/ap/internet-sharing/disable
  ```

#### 📊 Connection Tracking
- **Get connection history**
```bash
curl http://your-ip:8080/api/connections?limit=50
```

- **Get active connections**
```bash
curl http://your-ip:8080/api/connections/active
```

- **Get connection statistics**
```bash
curl http://your-ip:8080/api/connections/stats
```

- **Manually monitor connections**
```bash
curl -X POST http://your-ip:8080/api/connections/monitor
```

#### 📝 Log Management
- **View last N lines from log**
  ```bash
  curl http://your-ip:8080/api/logs?lines=10
  ```

- **View all log lines**
  ```bash
  curl http://your-ip:8080/api/logs
  ```

- **Download log file**
  ```bash
  curl -O http://your-ip:8080/api/logs/download
  ```

---

### 🛠️ API Testing Tools

**Recommended:**
1. **Swagger UI** (Built-in) - `http://192.168.4.1:8080/api/docs`
   - Interactive browser-based testing
   - No additional software needed
   - Complete documentation

2. **Third-Party Tools:**
   - Postman
   - Insomnia
   - curl (command line)
   - Any HTTP client

**OpenAPI Specification:**
The API follows OpenAPI 3.0 standards, accessible at: `http://192.168.4.1:8080/api/swagger.json`

### Swagger UI Quick Start

1. **After setup, access Swagger:**
   ```
   http://192.168.4.1:8080/api/docs
   ```

2. **Explore API endpoints** organized in namespaces:
   - `hosts` - DHCP host management
   - `ap` - Access Point configuration
   - `connections` - Connection tracking
   - `logs` - Application logs

3. **Try it out:**
   - Click any endpoint
   - Click "Try it out"
   - Fill in parameters
   - Click "Execute"
   - View response

4. **View schemas:**
   - See request/response formats
   - Understand data structures
   - Copy example JSON for your own tools

---

## 🚀 Installation

Choose the installation method that best fits your environment:

### 📡 Method 1: Online Installation (Recommended)

**Best for:** Systems with internet access. Fully automated setup with automatic package downloads.

#### Prerequisites
- Raspberry Pi with internet access
- sudo privileges

#### Installation Steps

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd dhcp_dashboard
   ```

2. **Run the automated setup:**
   ```bash
   sudo bash setup_pi.sh
   ```

3. **Follow the interactive prompts:**
   - Enter your desired Access Point name (SSID)
   - Enter your desired Access Point password (minimum 8 characters)
   - The script will handle everything else automatically

#### What the Online Setup Does
- ✅ Downloads and installs system packages (dnsmasq, hostapd, python3-pip)
- ✅ Downloads and installs Python dependencies
- ✅ Fixes Access Point setup issues (unmasks hostapd, resolves conflicts)
- ✅ Cleans existing DHCP hosts with improved pattern matching
- ✅ Sets up AP state persistence across reboots
- ✅ Resolves service conflicts (NetworkManager, wpa_supplicant)
- ✅ Creates systemd service for auto-start on boot
- ✅ Configures sudo permissions for system commands
- ✅ Starts the application automatically
- ✅ Displays access URL and service management commands

#### Expected Output
```
==========================================
INSTALLATION COMPLETED SUCCESSFULLY!
==========================================

Dashboard URL: http://192.168.4.1:8080
Your Access Point is now running:
  - SSID: RaspberryPi-AP
  - Password: [as configured]
  - AP IP: 192.168.4.1
```

---

### 🔌 Method 2: Offline Installation (No Internet)

**Best for:** Air-gapped systems, isolated networks, or systems without internet access.

#### Prerequisites
- Two Raspberry Pi systems: one with internet (for package preparation), one without
- USB drive or network transfer capability between systems
- sudo privileges on both systems

#### Step 1: Prepare Packages (On Connected System)

1. **Clone repository on connected system:**
   ```bash
   git clone <repository-url>
   cd dhcp_dashboard
   ```

2. **Pre-load all required packages:**
   ```bash
   sudo bash preload_packages.sh
   ```

   This creates `/var/cache/dhcp-dashboard-packages/` containing:
   - All required `.deb` packages (dnsmasq, hostapd, python3-pip)
   - Python packages from `requirements.txt`
   - Complete offline installation instructions

#### Step 2: Transfer Files to Offline System

1. **Copy the package cache:**
   ```bash
   # Using scp (if network available between systems)
   scp -r /var/cache/dhcp-dashboard-packages user@offline-pi:/tmp/

   # Or using USB drive
   cp -r /var/cache/dhcp-dashboard-packages /media/usb/
   # Then copy from USB to offline system
   ```

2. **Copy the application code:**
   ```bash
   # Copy the entire dhcp_dashboard directory to offline system
   scp -r dhcp_dashboard user@offline-pi:/home/user/
   ```

#### Step 3: Install on Offline System

1. **Navigate to the application directory:**
   ```bash
   cd /home/user/dhcp_dashboard
   ```

2. **Install system packages from cache:**
   ```bash
   cd /tmp/dhcp-dashboard-packages
   sudo dpkg -i *.deb
   sudo apt-get install -f -y  # Fix any dependency issues
   ```

3. **Install Python packages (if cached):**
   ```bash
   sudo pip3 install --no-index --find-links=/tmp/dhcp-dashboard-packages/python-packages -r requirements.txt --break-system-packages
   ```

4. **Run setup in offline mode:**
   ```bash
   cd /home/user/dhcp_dashboard
   sudo bash setup_pi.sh --offline
   ```

5. **Follow the interactive prompts:**
   - Enter your desired Access Point name (SSID)
   - Enter your desired Access Point password (minimum 8 characters)

#### Offline Mode Features
- ✅ Skips all internet-dependent operations (`apt-get update/upgrade`)
- ✅ Checks if packages are already installed before attempting installation
- ✅ Provides clear error messages if required packages are missing
- ✅ Works with pre-installed packages from the cache
- ✅ Same interactive AP configuration as online mode

#### Troubleshooting Offline Installation
- **Missing packages:** If `dpkg -i` fails, ensure all dependencies are in the cache
- **Python packages:** May need manual installation if cache is incomplete
- **Network issues:** Ensure all files are properly transferred

---

### 🔧 Method 3: Manual Installation

**Best for:** Custom installations, development environments, or when you need full control.

#### Prerequisites
- Raspberry Pi with internet access (for manual downloads)
- sudo privileges
- Basic Linux knowledge

#### Installation Steps

1. **Update system and install prerequisites:**
   ```bash
   sudo apt-get update
   sudo apt-get install -y dnsmasq hostapd python3-pip
   ```

2. **Clone repository:**
   ```bash
   git clone <repository-url>
   cd dhcp_dashboard
   ```

3. **Install Python dependencies:**
   ```bash
   pip3 install -r requirements.txt --break-system-packages
   ```

4. **Run the application manually:**
   ```bash
   sudo python3 dhcp_dashboard.py
   ```

5. **Access the dashboard:**
   - Open browser: `http://your-raspberry-pi-ip:8080`
   - Note: Manual mode doesn't configure AP automatically

#### Manual Mode Limitations
- No automatic AP configuration
- No systemd service setup
- No sudo permissions configuration
- Requires manual network setup
- Not recommended for production use

---

### 📋 Installation Method Comparison

| Feature | Online | Offline | Manual |
|---------|--------|---------|--------|
| **Internet Required** | ✅ Yes | ❌ No (pre-load required) | ✅ Yes |
| **Automation Level** | ⭐⭐⭐ Full | ⭐⭐⭐ Full | ⭐ Basic |
| **AP Auto-Setup** | ✅ Yes | ✅ Yes | ❌ No |
| **Systemd Service** | ✅ Yes | ✅ Yes | ❌ No |
| **Interactive Setup** | ✅ Yes | ✅ Yes | ❌ No |
| **Complexity** | ⭐⭐⭐ Simple | ⭐⭐ Medium | ⭐⭐⭐ Complex |
| **Best For** | New setups | Air-gapped systems | Development/Custom |

---

### ⚙️ Post-Installation Service Management

After successful installation, manage the service with systemd:

```bash
# Check service status
sudo systemctl status dhcp-dashboard

# Start the service
sudo systemctl start dhcp-dashboard

# Stop the service
sudo systemctl stop dhcp-dashboard

# Restart the service
sudo systemctl restart dhcp-dashboard

# View live logs
sudo journalctl -u dhcp-dashboard -f

# Disable auto-start on boot
sudo systemctl disable dhcp-dashboard

# Re-enable auto-start on boot
sudo systemctl enable dhcp-dashboard
```

### ⚙️ Service Management

After setup, manage the service with systemd:

```bash
# Check service status
sudo systemctl status dhcp-dashboard

# Start the service
sudo systemctl start dhcp-dashboard

# Stop the service
sudo systemctl stop dhcp-dashboard

# Restart the service
sudo systemctl restart dhcp-dashboard

# View live logs
sudo journalctl -u dhcp-dashboard -f

# Disable auto-start on boot
sudo systemctl disable dhcp-dashboard

# Re-enable auto-start on boot
sudo systemctl enable dhcp-dashboard
```

### 🔧 Enhanced Setup Features

The setup script has been enhanced with automatic fixes for common issues:

#### 🚫 **Automatic Issue Resolution**

**Access Point Setup Issues:**
- ✅ **Hostapd Service Masking** - Automatically unmasks hostapd service
- ✅ **NetworkManager Conflicts** - Stops and disables NetworkManager
- ✅ **wpa_supplicant Conflicts** - Configures to avoid wlan0 interference
- ✅ **Default Configuration** - Sets up proper hostapd defaults

**DHCP Host Cleanup:**
- ✅ **Improved Pattern Matching** - Finds all dhcp-host entries regardless of format
- ✅ **Comprehensive Cleanup** - Removes ANY line containing "dhcp-host="
- ✅ **Better Error Handling** - Fixed "integer expression expected" errors
- ✅ **Debug Output** - Shows exactly what's being cleaned

**State Persistence:**
- ✅ **AP State Memory** - Remembers if AP was enabled/disabled across reboots
- ✅ **Boot-time Management** - Automatically starts/stops AP based on saved state
- ✅ **State Manager Script** - `/usr/local/bin/ap-manager.sh` for manual control
- ✅ **Dashboard Integration** - Web interface controls permanent state

#### 🛠️ **Diagnostic & Fix Scripts**

If you encounter issues, additional diagnostic scripts are available:

```bash
# Diagnose AP setup issues
sudo bash diagnose_ap_setup.sh

# Diagnose DHCP host storage
sudo bash diagnose_dhcp_hosts.sh

# Fix Wi-Fi client setup (wlan1) issues
sudo bash fix_wifi_client_setup.sh

# Fix AP persistence issues
sudo bash fix_ap_persistence.sh

# Clean up DHCP hosts manually
sudo bash cleanup_dhcp_hosts.sh
```

#### 📡 **Access Point State Management**

The system now includes persistent AP state management:

**Manual AP Control:**
```bash
# Enable AP (remembers across reboots)
sudo /usr/local/bin/ap-manager.sh enable

# Disable AP (remembers across reboots)
sudo /usr/local/bin/ap-manager.sh disable

# Check current state
sudo /usr/local/bin/ap-manager.sh status
```

**How it works:**
- 🔄 **State File**: `/var/lib/dhcp-dashboard/ap_state` stores "enabled" or "disabled"
- 🚀 **Boot Service**: `ap-state-manager.service` runs on every boot
- 🎯 **Smart Logic**: Only starts AP if previously enabled, keeps disabled if previously disabled
- 🖥️ **Dashboard Sync**: Web interface changes are permanent

#### 🌐 **Network Setup Options**

The enhanced setup handles different network configurations:

**Option 1: Dual Wi-Fi (Recommended)**
- wlan0 = Access Point
- wlan1 = Wi-Fi Client (requires USB adapter)
- Full internet sharing capability

**Option 2: Ethernet + Wi-Fi AP**
- wlan0 = Access Point
- eth0 = Internet via Ethernet
- Internet sharing through wired connection

**Option 3: Single Wi-Fi**
- wlan0 = Either AP OR client mode
- Isolated network or client-only setup

---

## 🌐 Network Configuration

### 📡 Dual Wi-Fi Adapter Setup

**Interface Assignment:**
- **wlan0** (built-in): Access Point broadcasting your lab network
- **wlan1** (USB dongle): Wi-Fi client for internet connectivity
- **eth0** (ethernet): Wired devices via switch

When you configure through the web interface:

1. **Access Point (wlan0)** - Configure and start your lab network
   - Broadcasts SSID on wlan0
   - Static IP: `192.168.4.1/24`
   - DHCP range: `192.168.4.10-250`

2. **Wi-Fi Client (wlan1)** - Connect to external Wi-Fi
   - Use "Wi-Fi Configuration" form
   - Connects to internet/upstream network
   - Gets IP via DHCP from that network
   - **Requires USB Wi-Fi adapter**

3. **Internet Sharing** - Toggle on/off via web interface
   - **Enable**: Share internet from wlan1 to local network
     - Devices on wlan0/eth0 can access internet
     - Uses NAT/IP forwarding
   - **Disable**: Isolate local network (no internet)
     - Lab network is completely isolated
     - No external access

4. **Network Configuration** automatically handles:
   - Static IP `192.168.4.1/24` for wlan0 and eth0
   - DHCP client on wlan1
   - DNS server for local network
   - Unified subnet for AP clients
   - IP forwarding and NAT (when internet sharing enabled)

### 🔗 Network Topology (Dual Wi-Fi Adapter Setup)

```
    [Internet/Router]
           │
           │ (Wi-Fi)
           │
      ┌────┴────────────────────────────┐
      │    Raspberry Pi                 │
      │    wlan0: 192.168.4.1 (AP)     │
      │    wlan1: DHCP (Client)        │
      │    eth0:  192.168.4.1 (Wired)  │
      │                                 │
      │  ┌───────┬────────┬──────┐    │
      │  │ wlan0 │ wlan1  │ eth0 │    │
      └──┴───────┴────────┴──────┴─────┘
         │        │        │
         │        │        └──────────┐
         │        │                   │
         │     [Internet]         [Switch]
         │     Connection             │
         │                      ┌─────┴─────┐
    [Wi-Fi Clients]             │           │
    192.168.4.10-250      [Wired]     [Wired]
                          Device      Device
                          192.168.4.x 192.168.4.x
```

**Interface Details:**
- **wlan0 (built-in)**: Access Point @ `192.168.4.1`
  - Broadcasts your lab network SSID
  - Clients get IPs: `192.168.4.10-250`
  
- **wlan1 (USB dongle)**: Wi-Fi Client (optional)
  - Connects to upstream Wi-Fi for internet
  - Gets IP via DHCP from that network
  - Can share internet to lab network (if configured)
  
- **eth0 (ethernet)**: Wired network @ `192.168.4.1`
  - Connect switch for wired devices
  - Same subnet as wlan0

**Key Points:**
- **Unified Network**: All local devices on `192.168.4.x` subnet
- **Dual Wi-Fi**: wlan0 for AP, wlan1 for client (requires USB adapter)
- **DHCP Range**: `192.168.4.10` to `192.168.4.250`
- **Pi IP**: `192.168.4.1` (gateway for local network)
- **Internet**: Optional via wlan1 connection

---

## 📁 Configuration Files

The application manages:
- `/etc/dnsmasq.conf` - DHCP/DNS configuration (serves both interfaces)
- `/etc/hostapd/hostapd.conf` - Access Point configuration
- `/etc/dhcpcd.conf` - Network interface configuration (both wlan0 and eth0)
- `/etc/wpa_supplicant/wpa_supplicant.conf` - Wi-Fi client settings (when in client mode)
- `/etc/sysctl.conf` - Network configuration (IP forwarding disabled for local network)

---

## 📦 Requirements

- Python 3.x
- Flask
- dnsmasq (DHCP/DNS server)
- hostapd (Access Point software)
- sudo privileges for system operations

---

## 💡 Use Cases

### 🧪 Scenario 1: Isolated Network Lab
Create a completely isolated local network for testing without affecting your main network. Connect devices via Wi-Fi or Ethernet switch.

### 🤖 Scenario 2: IoT Development Environment
Set up a dedicated network for IoT device testing and development. All devices can communicate with each other on the same subnet.

### 🎓 Scenario 3: Network Training/Education
Perfect for teaching networking concepts (DHCP, DNS, subnetting) in a controlled, isolated environment.

### 🎒 Scenario 4: Portable Testing Environment
Bring your Raspberry Pi with a small switch to create an instant network anywhere - no internet required!

### 🛡️ Scenario 5: Security Testing Lab
Create isolated environments for penetration testing or security research without exposing your main network.

---

## 📄 Logging

### 📝 Application Logs
All operations are logged to `dhcp_dashboard.log` for troubleshooting and audit purposes.

### 📊 Connection Tracking
The application automatically tracks all device connections and disconnections:
- **Connection log**: `connection_log.json` - JSON format with detailed connection history
- **Information logged**:
  - Timestamp (ISO 8601 format)
  - Event type (connect/disconnect)
  - MAC address
  - IP address
  - Hostname (when available)
  - Interface (wlan0 for wireless, eth0 for wired)

**View in Dashboard**: The Connection History section displays:
- Recent connections table with all details
- Connection statistics (total connections, by interface, unique devices)
- Currently active connections count
- Real-time refresh capability

---

## 🔒 Security Note

⚠️ **Important**: Change the default secret key in `dhcp_dashboard.py` before deploying to production!

### How to Generate a Secure Secret Key

**Method 1: Using Python (Recommended)**
```bash
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

**Method 2: Using OpenSSL**
```bash
openssl rand -hex 32
```

**Method 3: Using /dev/urandom**
```bash
head -c 32 /dev/urandom | base64
```

### Update the Secret Key

1. Generate a key using one of the methods above
2. Open `dhcp_dashboard.py`
3. Replace the default key:

```python
# BEFORE (line 13)
app.secret_key = 'your_secret_key_here'  # Replace with a real secret key

# AFTER (example)
app.secret_key = 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6'
```

4. Restart the service:
```bash
sudo systemctl restart dhcp-dashboard
```

**Why is this important?**
- 🔐 Protects session data and cookies
- 🛡️ Prevents session hijacking
- ✅ Essential for production deployments
- ⚠️ Never commit your secret key to version control!

**Quick Update Example:**
```bash
# Generate new key
NEW_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')

# Update the file (backup first!)
sudo sed -i.bak "s/your_secret_key_here/$NEW_KEY/" dhcp_dashboard.py

# Restart service
sudo systemctl restart dhcp-dashboard
```

---

## 📜 License

See LICENSE file for details.

---

<div align="center">

## 👨‍💻 Developer

**Developed with ❤️ by [JPHsystems](https://github.com/jphermans)**

### 🌟 If you find this project useful, please give it a star!

---

### 📞 Support & Contact

For issues, questions, or contributions:
- 🐛 [Report Issues](../../issues)
- 💬 [Discussions](../../discussions)
- 📧 Contact: JPHsystems

---

**© 2025 JPHsystems. All rights reserved.**

</div>
