import flask
from flask import Flask, request, render_template_string, flash, redirect, url_for, jsonify, send_file
import subprocess
import re
import shutil
from datetime import datetime
import logging
import os
import time

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Replace with a real secret key

DNSMASQ_CONF = '/etc/dnsmasq.conf'
WPA_SUPPLICANT_CONF = '/etc/wpa_supplicant/wpa_supplicant.conf'
LOG_FILE = 'dhcp_dashboard.log'

logging.basicConfig(filename='dhcp_dashboard.log', level=logging.DEBUG)

def read_dhcp_hosts():
    try:
        with open(DNSMASQ_CONF, 'r') as f:
            content = f.read()
        hosts = re.findall(r'dhcp-host=([\w:]+),([\w.-]+)(?:,([\d.]+))?', content)
        logging.info(f"Read {len(hosts)} hosts from configuration")
        return hosts
    except Exception as e:
        logging.error(f"Error reading DHCP hosts: {str(e)}")
        return []

def write_dhcp_hosts(hosts):
    try:
        with open(DNSMASQ_CONF, 'r') as f:
            content = f.readlines()
        
        new_content = [line for line in content if not line.startswith('dhcp-host=')]
        for mac, hostname, ip in hosts:
            if ip:
                new_content.append(f'dhcp-host={mac},{hostname},{ip}\n')
            else:
                new_content.append(f'dhcp-host={mac},{hostname}\n')
        
        with open(DNSMASQ_CONF, 'w') as f:
            f.writelines(new_content)
        
        logging.info(f"Wrote {len(hosts)} hosts to configuration")
    except Exception as e:
        logging.error(f"Error writing DHCP hosts: {str(e)}")
        raise

def restart_dnsmasq():
    try:
        result = subprocess.run(['sudo', 'systemctl', 'restart', 'dnsmasq'], capture_output=True, text=True)
        if result.returncode != 0:
            status_output = get_dnsmasq_status()
            logging.error(f"Error restarting DNSMASQ: {result.stderr}\nStatus: {status_output}")
            raise Exception(f"Failed to restart DNSMASQ. Status: {status_output}")
        logging.info("DNSMASQ restarted successfully")
    except Exception as e:
        logging.error(f"Exception when restarting DNSMASQ: {str(e)}")
        raise

def get_dnsmasq_status():
    try:
        result = subprocess.run(['sudo', 'systemctl', 'status', 'dnsmasq'], capture_output=True, text=True)
        return result.stdout
    except Exception as e:
        logging.error(f"Error getting DNSMASQ status: {str(e)}")
        return "Unable to get DNSMASQ status"

def backup_dnsmasq_conf():
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{DNSMASQ_CONF}.backup_{timestamp}"
        shutil.copy2(DNSMASQ_CONF, backup_file)
        logging.info(f"Backup created: {backup_file}")
        return backup_file
    except Exception as e:
        logging.error(f"Error creating backup: {str(e)}")
        raise

def shutdown_pi():
    os.system("sudo shutdown -h now")


def update_wifi_settings(ssid, password):
    try:
        wpa_config = f'''
                ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
                update_config=1
                country=BE

                network={{
                    ssid="{ssid}"
                    psk="{password}"
                }}
        '''
        with open(WPA_SUPPLICANT_CONF, 'w') as f:
            f.write(wpa_config)
        
        # Restart the Wi-Fi interface
        subprocess.run(['sudo', 'ifconfig', 'wlan0', 'down'], check=True)
        time.sleep(1)
        subprocess.run(['sudo', 'ifconfig', 'wlan0', 'up'], check=True)
        time.sleep(2)
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'], check=True)
        
        # Wait for the connection to be established
        for _ in range(30):  # Wait up to 30 seconds
            result = subprocess.run(['iwgetid', '-r'], capture_output=True, text=True)
            if result.stdout.strip() == ssid:
                logging.info(f"Successfully connected to Wi-Fi network: {ssid}")
                return True
            time.sleep(1)
        
        logging.error(f"Failed to connect to Wi-Fi network: {ssid}")
        return False
    except Exception as e:
        logging.error(f"Error updating Wi-Fi settings: {str(e)}")
        return False

@app.route('/api/hosts', methods=['GET'])
def api_get_hosts():
    hosts = read_dhcp_hosts()
    return jsonify([{'mac': mac, 'hostname': hostname, 'ip': ip} for mac, hostname, ip in hosts])

@app.route('/api/hosts', methods=['POST'])
def api_add_host():
    data = request.json
    if not data or 'mac' not in data or 'hostname' not in data:
        return jsonify({'error': 'Missing required fields'}), 400
    
    mac = data['mac']
    hostname = data['hostname']
    ip = data.get('ip')
    
    hosts = read_dhcp_hosts()
    if any(h[0] == mac for h in hosts):
        return jsonify({'error': 'MAC address already exists'}), 400
    if any(h[1] == hostname for h in hosts):
        return jsonify({'error': 'Hostname already exists'}), 400
    
    hosts.append((mac, hostname, ip))
    try:
        write_dhcp_hosts(hosts)
        restart_dnsmasq()
        return jsonify({'message': 'Host added successfully'}), 201
    except Exception as e:
        logging.error(f"Error adding host via API: {str(e)}")
        return jsonify({'error': 'Failed to add host'}), 500

@app.route('/api/hosts/<mac>', methods=['DELETE'])
def api_remove_host(mac):
    hosts = read_dhcp_hosts()
    original_count = len(hosts)
    hosts = [h for h in hosts if h[0] != mac]
    if len(hosts) == original_count:
        return jsonify({'error': 'Host not found'}), 404
    
    try:
        write_dhcp_hosts(hosts)
        restart_dnsmasq()
        return jsonify({'message': 'Host removed successfully'}), 200
    except Exception as e:
        logging.error(f"Error removing host via API: {str(e)}")
        return jsonify({'error': 'Failed to remove host'}), 500

@app.route('/api/logs', methods=['GET'])
def api_get_logs():
    lines = request.args.get('lines', default=50, type=int)
    try:
        with open(LOG_FILE, 'r') as file:
            log_contents = file.readlines()
        
        # Get the last 'lines' number of log entries
        last_logs = log_contents[-lines:]
        
        return jsonify({'logs': last_logs})
    except Exception as e:
        logging.error(f"Error reading log file: {str(e)}")
        return jsonify({'error': 'Failed to read log file'}), 500

@app.route('/api/logs/download', methods=['GET'])
def api_download_logs():
    try:
        return send_file(LOG_FILE, as_attachment=True)
    except Exception as e:
        logging.error(f"Error downloading log file: {str(e)}")
        return jsonify({'error': 'Failed to download log file'}), 500


@app.route('/', methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            try:
                mac = request.form.get('mac')
                hostname = request.form.get('hostname')
                ip = request.form.get('ip') or None
                hosts = read_dhcp_hosts()
                if any(h[0] == mac for h in hosts):
                    flash(f"MAC address {mac} already exists. Edit the existing entry to update.")
                elif any(h[1] == hostname for h in hosts):
                    flash(f"Hostname {hostname} already exists. Choose a different hostname.")
                else:
                    hosts.append((mac, hostname, ip))
                    write_dhcp_hosts(hosts)
                    restart_dnsmasq()
                    flash("Host added successfully.")
            except Exception as e:
                flash(f"Error adding host: {str(e)}")
                logging.error(f"Error adding host: {str(e)}")
        elif action == 'restart':
            try:
                restart_dnsmasq()
                flash("DNSMASQ service restarted.")
            except Exception as e:
                flash(f"Error restarting DNSMASQ: {str(e)}")
        elif action == 'backup':
            try:
                backup_file = backup_dnsmasq_conf()
                flash(f"Backup created: {backup_file}")
            except Exception as e:
                flash(f"Error creating backup: {str(e)}")
        elif action == 'status':
            status = get_dnsmasq_status()
            flash(f"DNSMASQ Status:\n{status}")
        elif action == 'shutdown':
            return render_template_string('''
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Confirm Shutdown</title>
                    <style>
                        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
                        .warning { color: red; font-weight: bold; }

                        h1 { color: #343f48}

                        input[type=button], input[type=submit], input[type=reset] {
                        background-color: #343f48;
                        color: #ffd700;
                        font-size: 14px;
                        border: none; border-radius: 10px;
                        color: white;
                        padding: 10px 10px;
                        text-decoration: none;
                        margin: 4px 2px;
                        cursor: pointer;
                    }
                    input[type="submit"]:hover { background-color: red; color: yellow; font-weight: bold; }
                    
                    </style>
                </head>
                <body>
                    <h1>Confirm Shutdown</h1>
                    <p class="warning">Are you sure you want to shut down the Raspberry Pi?</p>
                    <p>This will terminate all services and you won't be able to access the device remotely until it's manually restarted.</p>
                    <form method="post">
                        <input type="hidden" name="action" value="confirm_shutdown">
                        <input type="submit" value="Yes, Shut Down">
                    </form><br>
                    <a href="{{ url_for('dashboard') }}">Cancel</a>
                
                </body>
                </html>
            ''')
        elif action == 'confirm_shutdown':
            flash("Shutting down the Raspberry Pi...")
            shutdown_pi()
        elif action == 'wifi':
            ssid = request.form.get('ssid')
            password = request.form.get('password')
            if update_wifi_settings(ssid, password):
                flash("Wi-Fi settings updated successfully. The Raspberry Pi has connected to the new network.", "success")
            else:
                flash("Failed to update Wi-Fi settings or connect to the new network.", "error")
    
    hosts = read_dhcp_hosts()
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DHCP/DNS Dashboard</title>
    <style>
        html, body {
            height: 100%;
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
        }
        .page-container {
            display: flex;
            flex-direction: column;
            min-height: 100vh;
        }
        .content-wrap {
            flex: 1 0 auto;
            padding: 20px;
        }
        body { font-family: Arial, sans-serif; }
        input[type="text"] { width: 200px; margin-bottom: 10px; }
        .flash { padding: 10px; background-color: #f0f0f0; margin-bottom: 20px; white-space: pre-wrap; }
        .danger { background-color: #ffdddd; color: #f44336; }
        .form-container {
            background-color: #f2f2f2;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            width: 300px;
        }
        h2 { color: #333; margin-bottom: 1.5rem; }
        form { display: flex; flex-direction: column; }
        label { margin-bottom: 0.5rem; color: #555; }
        input[type="text"] {
            padding: 0.5rem;
            margin-bottom: 1rem;
            border: 1px solid #ddd;
            border-radius: 14px;
        }
        input[type="submit"] {
            background-color:#343f48;
            color: #ffd700;
            padding: 0.75rem;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            font-size: 1rem;
            transition: background-color 0.3s;
        }
        input[type="submit"]:hover { background-color: #45a049; }
        .footer {
            flex-shrink: 0;
            background-color: #505e6b;
            color: #ffffff;
            text-align: center;
            padding: 10px;
            font-size: 20px;
        }
        
        .form-container-wrapper {
            display: flex;
            justify-content: space-between;
            gap: 20px; /* Adds space between the containers */
            max-width: 650px; /* Adjust this value as needed */
            margin-left: 0;                      
        }

        .form-container {
            flex: 1; /* Makes both containers take up equal width */
            background-color: #f2f2f2;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            box-sizing: border-box;
        }
        .form-container input[type="text"],
        .form-container input[type="password"] {
            width: 100%;
            padding: 0.5rem;
            margin-bottom: 1rem;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }

        @media (max-width: 650px) {
            .form-container-wrapper {
                flex-direction: column;
            }
            
            .form-container {
                flex: 1 1 auto;                  
                max-width: none;
            }
        }
            .responsive-table {
        width: 100%;
        margin-bottom: 20px;
        overflow-x: auto;
        }
        table {
            width: 100%;
            min-width: 600px; /* Ensures table doesn't get too narrow */
            border-collapse: collapse;
            
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
            text-align: center;
        }
        th {
            background-color: #343f48;
            color: #ffd700;
            white-space: nowrap;
        }
        tr:nth-child(even) {
            background-color: #f2f2f2;
        }
        .action-buttons {
            display: flex;
            gap: 5px;
        }
        .action-buttons input[type="submit"] {
            padding: 5px 10px;
            font-size: 0.9em;
        }
        
        @media screen and (max-width: 600px) {
            .responsive-table {
                overflow-x: scroll;
            }
            th, td {
                padding: 8px;
            }
            .action-buttons {
                flex-direction: column;
            }
        }
        
    .dhcp-hosts {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
        gap: 20px;
        width: 100%;
        margin-bottom: 30px; /* Increased space before Add New Host */
    }
    
    .host-card {
        background-color: #f2f2f2;
        border-radius: 8px;
        padding: 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .host-card h3 {
        margin-top: 0;
        color: #343f48;
        border-bottom: 2px solid #ffd700;
        padding-bottom: 10px;
        margin-bottom: 15px;
    }
    
    .host-info {
        margin-bottom: 20px;
    }
    
    .host-info strong {
        color: #343f48;
    }
    
        .host-actions {
            display: flex;
            justify-content: space-between;
            gap: 10px;
            margin-top: 15px;
        }
        
        .host-actions form {
            flex: 1;
        }
        
        .host-actions input[type="submit"] {
            width: 100%;
            padding: 10px 15px;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: background-color 0.3s ease;
        }
        
        .host-actions input[type="submit"]:hover {
            opacity: 0.9;
        }
        
        .edit-button {
            background-color: #343f48;
            color: #ffd700;
        }
        
        .remove-button {
            background-color: #e74c3c;
            color: white;
        }
        
        .host-actions input[type="submit"].remove-button:hover {
            background-color: #ff0000;
            color: yellow;
        }
    
    .host-actions input[type="submit"]:hover {
            background-color: #45a049;
    
    @media screen and (max-width: 600px) {
        .dhcp-hosts {
            grid-template-columns: 1fr;
        }
    }
    
    </style>
</head>
<body>
    <div class="page-container">
        <div class="content-wrap">
            <h1>DHCP/DNS Dashboard</h1>
            {% with messages = get_flashed_messages() %}
                {% if messages %}
                    {% for message in messages %}
                        <div class="flash">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            
            <h2>Current DHCP Hosts</h2>
            <div class="dhcp-hosts">
                {% for mac, hostname, ip in hosts %}
                <div class="host-card">
                    <h3>{{ hostname }}</h3>
                    <div class="host-info">
                        <p><strong>MAC Address:</strong> {{ mac }}</p>
                        <p><strong>IP Address:</strong> {{ ip if ip else 'Dynamic' }}</p>
                    </div>
                    <div class="host-actions">
                    <form method="get" action="{{ url_for('edit_host') }}">
                        <input type="hidden" name="mac" value="{{ mac }}" />
                        <input type="submit" value="Edit" class="edit-button" />
                    </form>
                    <form onsubmit="return confirmRemove('{{ hostname }}')" method="post" action="{{ url_for('remove_host') }}">
                        <input type="hidden" name="mac" value="{{ mac }}" />
                        <input type="submit" value="Remove" class="remove-button" />
                    </form>
                </div>
                </div>
                {% endfor %}
            </div>
            <br>
            <div class="form-container-wrapper">
                <div class="form-container">
                    <h2>Add New Host</h2>
                    <form method="post">
                        <input type="hidden" name="action" value="add" />
                        <label for="mac">MAC Address:</label>
                        <input type="text" id="mac" name="mac" required />
                        <label for="hostname">Hostname:</label>
                        <input type="text" id="hostname" name="hostname" required />
                        <label for="ip">IP Address (optional):</label>
                        <input type="text" id="ip" name="ip" />
                        <input type="submit" value="Add Host" />
                    </form>
                </div>
                
                <div class="form-container">
                    <h2>Wi-Fi Configuration</h2>
                    <form method="post">
                        <input type="hidden" name="action" value="wifi">
                        <label for="ssid">Wi-Fi SSID:</label>
                        <input type="text" id="ssid" name="ssid" required>
                        <label for="password">Wi-Fi Password:</label>
                        <input type="password" id="password" name="password" required>
                        <input type="submit" value="Update Wi-Fi Settings">
                    </form>
                </div>
            </div>
            
            <h2>DNSMASQ Management</h2>
            <form method="post" style="display: inline;">
                <input type="hidden" name="action" value="restart" />
                <input type="submit" value="Restart DNSMASQ" />
            </form>
            <form method="post" style="display: inline; margin-left: 10px;">
                <input type="hidden" name="action" value="backup" />
                <input type="submit" value="Backup Configuration" />
            </form>
            <form method="post" style="display: inline; margin-left: 10px;">
                <input type="hidden" name="action" value="status" />
                <input type="submit" value="Check DNSMASQ Status" />
            </form>
                                  
                     
            
            <h2>System Management</h2>
            <form method="post" style="display: inline;">
                <input type="hidden" name="action" value="shutdown" />
                <input type="submit" value="Shutdown Raspberry Pi" class="danger" />
            </form>
        </div>
        
        <footer class="footer">
            <p>&copy; <span id="current-year"></span> JPHsystems. All rights reserved.</p>
        </footer>

        <script>
            document.getElementById('current-year').textContent = new Date().getFullYear();
                                  
            function confirmRemove(hostname) {
                return confirm(`Are you sure you want to remove the host "${hostname}"?`);
            }

        </script>
    </div>
</body>
</html>
    ''', hosts=hosts)

@app.route('/edit', methods=['GET', 'POST'])
def edit_host():
    if request.method == 'POST':
        old_mac = request.form.get('old_mac')
        new_mac = request.form.get('new_mac')
        new_hostname = request.form.get('new_hostname')
        new_ip = request.form.get('new_ip') or None
        
        hosts = read_dhcp_hosts()
        updated_hosts = [(new_mac, new_hostname, new_ip) if h[0] == old_mac else h for h in hosts]
        
        if hosts == updated_hosts:
            flash("No changes were made.")
        else:
            write_dhcp_hosts(updated_hosts)
            restart_dnsmasq()
            flash("Host updated successfully.")
        
        return redirect(url_for('dashboard'))
    
    mac = request.args.get('mac')
    hosts = read_dhcp_hosts()
    host = next((h for h in hosts if h[0] == mac), None)
    
    if not host:
        flash("Host not found.")
        return redirect(url_for('dashboard'))
    
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Edit DHCP Host</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #f0f0f0;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .container {
            background-color: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            width: 350px;
        }
        h1 {
            color: #333;
            margin-bottom: 1.5rem;
            font-size: 1.5rem;
        }
        form {
            display: flex;
            flex-direction: column;
        }
        label {
            margin-bottom: 0.5rem;
            color: #555;
        }
        input[type="text"] {
            padding: 0.5rem;
            margin-bottom: 1rem;
            border: 1px solid #ddd;
            border-radius: 14px;
            width: 100%;
            box-sizing: border-box;
        }
        input[type="submit"] {
            background-color: #343f48;
            color: #ffd700;
            padding: 0.75rem;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 1rem;
            transition: background-color 0.3s;
        }
        input[type="submit"]:hover {
            background-color: #45a049;
        }
        .cancel-link {
            display: inline-block;
            margin-top: 1rem;
            color: #666;
            text-decoration: none;
            transition: color 0.3s;
        }
        .cancel-link:hover {
            color: #333;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Edit DHCP Host</h1>
        <form method="post">
            <input type="hidden" name="old_mac" value="{{ host[0] }}">
            
            <label for="new_mac">MAC Address:</label>
            <input type="text" id="new_mac" name="new_mac" value="{{ host[0] }}" required>
            
            <label for="new_hostname">Hostname:</label>
            <input type="text" id="new_hostname" name="new_hostname" value="{{ host[1] }}" required>
            
            <label for="new_ip">IP Address:</label>
            <input type="text" id="new_ip" name="new_ip" value="{{ host[2] or '' }}">
            
            <input type="submit" value="Update Host">
        </form>
        <a href="{{ url_for('dashboard') }}" class="cancel-link">Cancel</a>
    </div>
</body>
</html>
    ''', host=host)

@app.route('/remove', methods=['POST'])
def remove_host():
    try:
        mac = request.form.get('mac')
        hosts = read_dhcp_hosts()
        original_count = len(hosts)
        hosts = [h for h in hosts if h[0] != mac]
        if len(hosts) == original_count:
            flash(f"No host found with MAC address {mac}")
            logging.warning(f"Attempted to remove non-existent host with MAC {mac}")
        else:
            write_dhcp_hosts(hosts)
            restart_dnsmasq()
            flash("Host removed successfully.")
            logging.info(f"Removed host with MAC {mac}")
    except Exception as e:
        flash(f"Error removing host: {str(e)}")
        logging.error(f"Error removing host: {str(e)}")
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
    app.config['FORCE_JSON'] = True
