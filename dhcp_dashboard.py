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
<html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Confirm Shutdown</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        margin: 0;
                        padding: 20px;
                        background-color: #f5f5f5;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                    }
                    .container {
                        background-color: white;
                        padding: 30px;
                        border-radius: 10px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                        max-width: 400px;
                        width: 100%;
                    }
                    h1 {
                        color: #343f48;
                        margin-top: 0;
                        font-size: 24px;
                    }
                    .warning {
                        color: red;
                        font-weight: bold;
                        font-size: 18px;
                    }
                    p {
                        font-size: 16px;
                        line-height: 1.5;
                    }
                    input[type="submit"] {
                        background-color: #343f48;
                        color: #ffd700;
                        font-size: 16px;
                        border: none;
                        border-radius: 5px;
                        padding: 12px 20px;
                        cursor: pointer;
                        width: 100%;
                        margin-top: 20px;
                    }
                    input[type="submit"]:hover {
                        background-color: red;
                        color: yellow;
                        font-weight: bold;
                    }
                    .cancel-link {
                        display: block;
                        text-align: center;
                        margin-top: 20px;
                        color: #343f48;
                        text-decoration: none;
                        font-size: 16px;
                    }
                    .cancel-link:hover {
                        text-decoration: underline;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Confirm Shutdown</h1>
                    <p class="warning">Are you sure you want to shut down the Raspberry Pi?</p>
                    <p>This will terminate all services and you won't be able to access the device remotely until it's manually restarted.</p>
                    <form method="post">
                        <input type="hidden" name="action" value="confirm_shutdown">
                        <input type="submit" value="Yes, Shut Down">
                    </form>
                    <a href="{{ url_for('dashboard') }}" class="cancel-link">Cancel</a>
                </div>
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
                flash("Wi-Fi settings updated successfully. The Raspberry Pi has connected to the new network.",
                      "success")
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
        :root {
            --bg-color: #eef2f6;
            --card-bg: #ffffff;
            --primary: #343f48;
            --accent: #ffd700;
            --text-color: #2b3947;
            --danger: #f44336;
            --danger-hover: #d32f2f;
            --radius: 18px;
            --shadow: 0 18px 30px rgba(23, 43, 77, 0.1);
        }

        * {
            box-sizing: border-box;
        }

        html, body {
            height: 100%;
        }

        body {
            margin: 0;
            font-family: 'Segoe UI', Roboto, Arial, sans-serif;
            background: var(--bg-color);
            color: var(--text-color);
            display: flex;
        }

        a {
            color: inherit;
        }

        .page-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            min-height: 100vh;
        }

        .content-wrap {
            flex: 1;
            width: min(1120px, 100%);
            margin: 0 auto;
            padding: clamp(20px, 4vw, 48px) clamp(16px, 6vw, 56px) clamp(60px, 8vw, 84px);
            display: flex;
            flex-direction: column;
            gap: clamp(24px, 4vw, 40px);
        }

        h1 {
            margin: 0;
            font-size: clamp(1.8rem, 1.4rem + 2vw, 3rem);
            text-align: center;
            color: var(--primary);
            letter-spacing: 0.5px;
        }

        h2 {
            margin: 0;
            font-size: clamp(1.3rem, 1.1rem + 1vw, 2rem);
            color: var(--primary);
        }

        h3 {
            margin: 0;
            font-size: 1.2rem;
            color: var(--primary);
        }

        .flash-stack {
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-top: clamp(12px, 3vw, 18px);
        }

        .flash {
            background: #fff6d1;
            border-left: 5px solid var(--accent);
            padding: 14px 18px;
            border-radius: 12px;
            box-shadow: 0 10px 25px rgba(52, 63, 72, 0.08);
            white-space: pre-wrap;
            font-size: 0.95rem;
        }

        .section {
            background: var(--card-bg);
            border-radius: var(--radius);
            padding: clamp(20px, 3vw, 32px);
            box-shadow: var(--shadow);
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .section > p {
            margin: 0;
        }

        .host-grid {
            display: grid;
            gap: 20px;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        }

        .host-card {
            background: linear-gradient(160deg, #ffffff 0%, #f7f9fc 100%);
            border-radius: var(--radius);
            padding: 22px;
            box-shadow: inset 0 0 0 1px rgba(52, 63, 72, 0.08);
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .host-card h3 {
            border-bottom: 2px solid rgba(255, 215, 0, 0.45);
            padding-bottom: 12px;
        }

        .host-info p {
            margin: 6px 0;
            font-size: 0.98rem;
        }

        .host-info strong {
            color: var(--primary);
        }

        .empty-state {
            padding: 18px;
            background: rgba(52, 63, 72, 0.05);
            border-radius: 14px;
            font-size: 1rem;
        }

        .host-actions {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }

        .host-actions form {
            flex: 1 1 130px;
        }

        .forms-grid {
            display: grid;
            gap: 24px;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        }

        .form-card {
            background: linear-gradient(150deg, rgba(255, 255, 255, 0.95) 0%, rgba(239, 244, 249, 0.95) 100%);
            border-radius: var(--radius);
            padding: 24px;
            box-shadow: inset 0 0 0 1px rgba(52, 63, 72, 0.06);
            display: flex;
            flex-direction: column;
            gap: 18px;
        }

        .form-card form {
            display: flex;
            flex-direction: column;
            gap: 14px;
        }

        label {
            font-weight: 600;
            color: var(--primary);
            font-size: 0.95rem;
        }

        input[type="text"],
        input[type="password"] {
            padding: 12px 14px;
            border-radius: 12px;
            border: 1px solid rgba(52, 63, 72, 0.2);
            font-size: 1rem;
            transition: border 0.2s ease, box-shadow 0.2s ease;
        }

        input[type="text"]:focus,
        input[type="password"]:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(52, 63, 72, 0.15);
        }

        button,
        input[type="submit"] {
            background: var(--primary);
            color: var(--accent);
            border: none;
            border-radius: 999px;
            padding: 12px 20px;
            font-size: 0.95rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease, color 0.2s ease;
            width: 100%;
        }

        button:hover,
        input[type="submit"]:hover {
            background: #212a32;
            color: #fff7bf;
            transform: translateY(-1px);
            box-shadow: 0 14px 24px rgba(33, 42, 50, 0.18);
        }

        .danger {
            background: var(--danger);
            color: #fff;
        }

        .danger:hover {
            background: var(--danger-hover);
            color: #fff;
        }

        .management-buttons {
            display: flex;
            flex-wrap: wrap;
            gap: 14px;
        }

        .management-buttons form {
            flex: 1 1 220px;
        }

        footer {
            background: var(--primary);
            color: #fff;
            text-align: center;
            padding: 18px 16px;
            font-size: 0.95rem;
        }

        @media (max-width: 900px) {
            .content-wrap {
                padding: clamp(20px, 4vw, 32px);
            }
        }

        @media (max-width: 640px) {
            .host-actions {
                flex-direction: column;
            }

            .host-actions form {
                flex: 1 1 auto;
            }

            button,
            input[type="submit"] {
                width: 100%;
            }

            .forms-grid {
                grid-template-columns: 1fr;
            }

            .management-buttons form {
                flex: 1 1 100%;
            }
        }

        @media (max-width: 420px) {
            .section {
                padding: 18px;
            }

            .host-card,
            .form-card {
                padding: 20px;
            }
        }
    </style>
</head>
<body>
    <div class="page-container">
        <div class="content-wrap">
            <header>
                <h1>DHCP/DNS Dashboard</h1>
                {% with messages = get_flashed_messages() %}
                    {% if messages %}
                        <div class="flash-stack">
                            {% for message in messages %}
                                <div class="flash">{{ message }}</div>
                            {% endfor %}
                        </div>
                    {% endif %}
                {% endwith %}
            </header>

            <section class="section">
                <h2>Current DHCP Hosts</h2>
                {% if hosts %}
                    <div class="host-grid">
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
                                    <input type="submit" value="Edit" />
                                </form>
                                <form onsubmit="return confirmRemove('{{ hostname }}')" method="post" action="{{ url_for('remove_host') }}">
                                    <input type="hidden" name="mac" value="{{ mac }}" />
                                    <input type="submit" value="Remove" />
                                </form>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                {% else %}
                    <p class="empty-state">No DHCP host entries found. Add a host below to get started.</p>
                {% endif %}
            </section>

            <section class="section">
                <h2>Network Configuration</h2>
                <div class="forms-grid">
                    <div class="form-card">
                        <h3>Add New Host</h3>
                        <form method="post">
                            <input type="hidden" name="action" value="add" />
                            <label for="mac">MAC Address</label>
                            <input type="text" id="mac" name="mac" required />

                            <label for="hostname">Hostname</label>
                            <input type="text" id="hostname" name="hostname" required />

                            <label for="ip">IP Address (optional)</label>
                            <input type="text" id="ip" name="ip" />

                            <input type="submit" value="Add Host" />
                        </form>
                    </div>

                    <div class="form-card">
                        <h3>Wi-Fi Configuration</h3>
                        <form method="post">
                            <input type="hidden" name="action" value="wifi">
                            <label for="ssid">Wi-Fi SSID</label>
                            <input type="text" id="ssid" name="ssid" required>

                            <label for="password">Wi-Fi Password</label>
                            <input type="password" id="password" name="password" required>

                            <input type="submit" value="Update Wi-Fi Settings">
                        </form>
                    </div>
                </div>
            </section>

            <section class="section">
                <h2>DNSMASQ Management</h2>
                <div class="management-buttons">
                    <form method="post">
                        <input type="hidden" name="action" value="restart" />
                        <input type="submit" value="Restart DNSMASQ" />
                    </form>
                    <form method="post">
                        <input type="hidden" name="action" value="backup" />
                        <input type="submit" value="Backup Configuration" />
                    </form>
                    <form method="post">
                        <input type="hidden" name="action" value="status" />
                        <input type="submit" value="Check DNSMASQ Status" />
                    </form>
                </div>
            </section>

            <section class="section">
                <h2>System Management</h2>
                <div class="management-buttons">
                    <form method="post">
                        <input type="hidden" name="action" value="shutdown" />
                        <input type="submit" value="Shutdown Raspberry Pi" class="danger" />
                    </form>
                </div>
            </section>
        </div>

        <footer class="footer">
            <p>&copy; <span id="current-year"></span> JPHsystems. All rights reserved.</p>
        </footer>
    </div>

    <script>
        document.getElementById('current-year').textContent = new Date().getFullYear();

        function confirmRemove(hostname) {
            return confirm(`Are you sure you want to remove the host "${hostname}"?`);
        }
    </script>
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
