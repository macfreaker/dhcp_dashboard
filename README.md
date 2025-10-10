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
- 📡 **Wireless Access Point** broadcasting your own Wi-Fi network
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

- **DNSMASQ Service Control**
  - Restart the dnsmasq service
  - Check dnsmasq status
  - Create timestamped backups of the configuration file

- **Wi-Fi Client Configuration**
  - Connect to existing Wi-Fi networks as a client
  - Update Wi-Fi SSID and password through the web interface
  - Automatically reconnect to new networks

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

## 🚀 Quick Start

### ⚡ Automated Setup (Recommended)

Use the automated setup script for complete installation and auto-start configuration:

```bash
# Clone this repository
git clone <repository-url>
cd dhcp_dashboard

# Run the setup script (requires sudo)
sudo bash setup_pi.sh
```

**The setup script will:**
- ✅ Install all required packages (dnsmasq, hostapd, python3-pip)
- ✅ Install Python dependencies from requirements.txt
- ✅ Create systemd service for auto-start on boot
- ✅ Configure sudo permissions for system commands
- ✅ Start the application automatically
- ✅ Display access URL and service management commands

### 🔧 Manual Setup

If you prefer manual installation:

1. **Install prerequisites:**
   ```bash
   sudo apt-get update
   sudo apt-get install -y dnsmasq hostapd python3-pip
   ```

2. **Clone and install dependencies:**
   ```bash
   git clone <repository-url>
   cd dhcp_dashboard
   pip3 install -r requirements.txt
   ```

3. **Run manually:**
   ```bash
   sudo python3 dhcp_dashboard.py
   ```
   *Note: sudo required for system-level network configuration*

4. **Access the dashboard:**
   - Open browser: `http://your-raspberry-pi-ip:8080`

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

---

## 🌐 Network Configuration

### 📡 Access Point Mode Setup

When you configure the Access Point through the web interface, the application automatically:

1. **Configures hostapd** - Creates wireless access point on `wlan0`
2. **Sets up network interfaces** - Assigns static IP `192.168.4.1/24` to both `wlan0` and `eth0`
3. **Configures dnsmasq** - DHCP server for all devices (`192.168.4.10-192.168.4.250`)
4. **Unified network** - Both wireless and wired devices on same subnet
5. **No internet routing** - Isolated local network for testing/development

### 🔗 Network Topology

```
                    ┌─────────────────────┐
                    │   Raspberry Pi      │
                    │   (192.168.4.1)     │
                    │                     │
                    │  ┌──────┬──────┐   │
                    │  │wlan0 │ eth0 │   │
                    └──┴──────┴──────┴───┘
                       │      │
          ┌────────────┘      └──────────┐
          │                               │
    [Wi-Fi Clients]                  [Switch]
    192.168.4.10-250                      │
                                    ┌─────┴─────┐
                                    │           │
                              [Wired Device] [Wired Device]
                              192.168.4.x    192.168.4.x
```

**Key Points:**
- **Unified Network**: All devices (wireless + wired) on `192.168.4.x` subnet
- **No Internet**: Isolated local network without external routing
- **DHCP Range**: `192.168.4.10` to `192.168.4.250`
- **Pi IP**: `192.168.4.1` (gateway for local network)
- **Use Cases**: Network testing, IoT development, isolated lab environments

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

⚠️ **Important**: Change the default secret key in `dhcp_dashboard.py` before deploying:
```python
app.secret_key = 'your_secret_key_here'  # Replace with a strong secret key
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

**© 2024 JPHsystems. All rights reserved.**

</div>
