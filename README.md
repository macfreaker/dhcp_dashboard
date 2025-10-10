# Dashboard for DHCP/DNS on Raspberry PI

A Flask web application that provides a comprehensive dashboard for managing DHCP/DNS settings on a Raspberry Pi running dnsmasq. This tool makes it easy to manage network devices through both a web interface and RESTful API.

## Features

### 🌐 Web Dashboard
- **DHCP Host Management**
  - Add new hosts with MAC addresses, hostnames, and optional static IP addresses
  - Edit existing host configurations
  - Remove hosts from the DHCP server
  - View all configured hosts in a responsive card-based layout

- **DNSMASQ Service Control**
  - Restart the dnsmasq service
  - Check dnsmasq status
  - Create timestamped backups of the configuration file

- **Wi-Fi Configuration**
  - Update Wi-Fi SSID and password through the web interface
  - Automatically reconnect to new networks

- **System Management**
  - Shutdown the Raspberry Pi remotely through the web interface
  - Includes confirmation screen for safety

### 🔌 RESTful API Endpoints

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

#### Log Management
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

### 🛠️ Third-Party Tools
You can use tools like Postman, Insomnia, or any HTTP client to interact with the API endpoints.

## Installation

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Ensure dnsmasq is installed:
   ```bash
   sudo apt-get install dnsmasq
   ```

4. Run the application:
   ```bash
   python dhcp_dashboard.py
   ```

5. Access the dashboard at: `http://your-raspberry-pi-ip:8080`

## Configuration Files

The application manages:
- `/etc/dnsmasq.conf` - DHCP/DNS configuration
- `/etc/wpa_supplicant/wpa_supplicant.conf` - Wi-Fi settings

## Requirements

- Python 3.x
- Flask
- dnsmasq
- sudo privileges for system operations

## Logging

All operations are logged to `dhcp_dashboard.log` for troubleshooting and audit purposes.

## Security Note

⚠️ **Important**: Change the default secret key in `dhcp_dashboard.py` before deploying:
```python
app.secret_key = 'your_secret_key_here'  # Replace with a strong secret key
```

## License

See LICENSE file for details.
