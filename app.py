import json
import random
import datetime
import ipaddress
import math
import time
import threading
import os
import shutil
import requests
from flask import Flask, render_template, request, jsonify, send_file


app = Flask(__name__)

# Global variables
telemetry_thread = None
stop_generation = threading.Event()
generated_files = []
generated_macs = []  # New list to store generated MAC addresses

# Updated default config
default_config = {
    "CPUUsage_range": {"normal": (0, 75), "medium": (75, 90), "extreme": (90, 100)},
    "MemoryUsed_range": {"normal": (0, 50), "medium": (50, 80), "extreme": (80, 100)},  # Now in percentage
    "LOAD_AVG_ATOM_range": {"normal": (0, 70), "medium": (70, 85), "extreme": (85, 100)},
    "UpTime_range": {"normal": (432000, 518400), "medium": (172800, 432000), "extreme": (0, 172800)},
    "NoiseFloor_2G_range": {"normal": (-75, -65), "medium": (-85, -75), "extreme": (-100, -85)},
    "NoiseFloor_5G_range": {"normal": (-80, -75), "medium": (-90, -80), "extreme": (-100, -90)},
    "RSSI_range": {"normal": (-55, 0), "medium": (-70, -55), "extreme": (-100, -70)},
    "ConnectedClients_2G_range": {"normal": (3, 10), "medium": (1, 3), "extreme": (0, 1)},
    "ConnectedClients_5G_range": {"normal": (5, 20), "medium": (2, 5), "extreme": (0, 2)},
    "PacketsSent_2G_range": {"normal": (1, 50), "medium": (0, 1), "extreme": (0, 0)},
    "PacketsSent_5G_range": {"normal": (1, 500), "medium": (0, 1), "extreme": (0, 0)},
    "PacketsReceived_2G_range": {"normal": (50, 100), "medium": (1, 50), "extreme": (0, 1)},
    "PacketsReceived_5G_range": {"normal": (350, 700), "medium": (1, 350), "extreme": (0, 1)},
    "ErrorsSent_range": {"normal": (0, 0), "medium": (1, 3), "extreme": (3, 5)},
    "ProcessCPU_range": {"normal": (0, 2), "medium": (2, 5), "extreme": (5, 10)},
    "ProcessMem_range": {"normal": (0, 20), "medium": (20, 50), "extreme": (50, 100)}
}

TOTAL_MEMORY = 1048576  # 1GB in KB

def generate_mac_sequence(num_devices):
    base_mac = [random.randint(0, 255) for _ in range(6)]
    macs = []
    for i in range(num_devices):
        new_mac = base_mac.copy()
        last_four = (int.from_bytes(bytes(new_mac[-2:]), 'big') + i * 3) % (256 * 256)
        new_mac[-2:] = list(last_four.to_bytes(2, 'big'))
        macs.append(':'.join([f'{x:02x}' for x in new_mac]))
    return macs

def generate_cmmac(mac):
    mac_parts = [int(part, 16) for part in mac.split(':')]
    last_four = (int.from_bytes(bytes(mac_parts[-2:]), 'big') - 2) % (256 * 256)
    mac_parts[-2:] = list(last_four.to_bytes(2, 'big'))
    return ':'.join([f'{x:02x}' for x in mac_parts])

def generate_ipv4():
    return str(ipaddress.IPv4Address(random.randint(0, 2**32 - 1)))

def generate_random_value(range_value, device_type):
    lower, upper = range_value[device_type]
    if isinstance(lower, int) and isinstance(upper, int):
        return random.randint(lower, upper)
    else:
        return random.uniform(lower, upper)

def generate_telemetry_data(device, current_time, config):
    data = [
        {"Device.Time.CurrentLocalTime": current_time.strftime("%Y-%m-%d %H:%M:%S")},
        {"Profile.Name": "RDKB_Profile"},
        {"Device.DeviceInfo.ModelName": "CGA437TTCH3"},
        {"Device.DeviceInfo.Manufacturer": "Technicolor"},
        {"Device.DeviceInfo.MACAddress": device["mac"]},
        {"Device.DeviceInfo.CMMAC": device["CMMAC"]},
        {"Device.DeviceInfo.CMTSMAC": device["CMTSMAC"]},
        {"Device.DeviceInfo.SoftwareVersion": device["SoftwareVersion"]},
        {"Device.DeviceInfo.X_COMCAST-COM_WAN_IP": device["WAN_IP"]},
    ]

    device_type = device["type"]

    # CPU Usage
    cpu_usage = generate_random_value(config['CPUUsage_range'], device_type)
    data.append({"Device.DeviceInfo.ProcessStatus.CPUUsage": str(int(cpu_usage))})

    # Memory Status
    memory_used_percent = generate_random_value(config['MemoryUsed_range'], device_type)
    used_memory = int(TOTAL_MEMORY * memory_used_percent / 100)
    free_memory = TOTAL_MEMORY - used_memory
    data.extend([
        {"Device.DeviceInfo.MemoryStatus.Total": str(TOTAL_MEMORY)},
        {"Device.DeviceInfo.MemoryStatus.Used": str(used_memory)},
        {"Device.DeviceInfo.MemoryStatus.Free": str(free_memory)}
    ])

    # Load Average
    load_avg = generate_random_value(config['LOAD_AVG_ATOM_range'], device_type)
    data.append({"LOAD_AVG_ATOM_split": f"{load_avg:.2f}"})

    # Uptime
    uptime = generate_random_value(config['UpTime_range'], device_type)
    data.append({"Device.DeviceInfo.UpTime": str(int(uptime))})

    # WiFi Data
    data.extend([
        {"Device.WiFi.Radio.1.Enable": "1"},
        {"Device.WiFi.Radio.2.Enable": "1"},
        {"Device.WiFi.SSID.1.SSID": "TCH-2.4G"},
        {"Device.WiFi.SSID.2.SSID": "TCH-5G"},
        {"Device.WiFi.Radio.1.OperatingChannelBandwidth": "40MHz"},
        {"Device.WiFi.Radio.2.OperatingChannelBandwidth": "160MHz"},
        {"Device.WiFi.Radio.1.Channel": str(random.randint(1, 11))},
        {"Device.WiFi.Radio.2.Channel": str(random.choice([36, 40, 44, 48, 149, 153, 157, 161, 165]))},
    ])

    # Noise Floor
    noise_floor_2g = generate_random_value(config['NoiseFloor_2G_range'], device_type)
    noise_floor_5g = generate_random_value(config['NoiseFloor_5G_range'], device_type)
    data.extend([
        {"Device.WiFi.Radio.1.Stats.X_COMCAST-COM_NoiseFloor": str(int(noise_floor_2g))},
        {"Device.WiFi.Radio.2.Stats.X_COMCAST-COM_NoiseFloor": str(int(noise_floor_5g))},
    ])

    # Connected Clients
    clients_2g = generate_random_value(config['ConnectedClients_2G_range'], device_type)
    clients_5g = generate_random_value(config['ConnectedClients_5G_range'], device_type)
    data.extend([
        {"Device.WiFi.SSID.1.ConnectedClients": str(int(clients_2g))},
        {"Device.WiFi.SSID.2.ConnectedClients": str(int(clients_5g))},
    ])

    # RSSI
    rssi_2g = ','.join([str(int(generate_random_value(config['RSSI_range'], device_type))) for _ in range(int(clients_2g))])
    rssi_5g = ','.join([str(int(generate_random_value(config['RSSI_range'], device_type))) for _ in range(int(clients_5g))])
    data.extend([
        {"Device.WiFi.SSID.1.RSSI_split": rssi_2g + ','},
        {"Device.WiFi.SSID.2.RSSI_split": rssi_5g + ','},
    ])

    # Packets Sent
    packets_sent_2g = ','.join([str(int(generate_random_value(config['PacketsSent_2G_range'], device_type))) for _ in range(int(clients_2g))])
    packets_sent_5g = ','.join([str(int(generate_random_value(config['PacketsSent_5G_range'], device_type))) for _ in range(int(clients_5g))])
    data.extend([
        {"Device.WiFi.SSID.1.Stats.PacketsSent": packets_sent_2g + ','},
        {"Device.WiFi.SSID.2.Stats.PacketsSent": packets_sent_5g + ','},
    ])

    # Packets Received
    packets_received_2g = ','.join([str(int(generate_random_value(config['PacketsReceived_2G_range'], device_type))) for _ in range(int(clients_2g))])
    packets_received_5g = ','.join([str(int(generate_random_value(config['PacketsReceived_5G_range'], device_type))) for _ in range(int(clients_5g))])
    data.extend([
        {"Device.WiFi.SSID.1.Stats.PacketsReceived": packets_received_2g + ','},
        {"Device.WiFi.SSID.2.Stats.PacketsReceived": packets_received_5g + ','},
    ])

    # Errors Sent
    errors_sent_2g = ','.join([str(int(generate_random_value(config['ErrorsSent_range'], device_type))) for _ in range(int(clients_2g))])
    errors_sent_5g = ','.join([str(int(generate_random_value(config['ErrorsSent_range'], device_type))) for _ in range(int(clients_5g))])
    data.extend([
        {"Device.WiFi.SSID.1.Stats.ErrorsSent": errors_sent_2g + ','},
        {"Device.WiFi.SSID.2.Stats.ErrorsSent": errors_sent_5g + ','},
    ])

    # Process stats
    processes = ["telemetry2_0", "CcspEthAgent", "OneWifi", "CcspTandDSsp", "sm", "cujo-agent", "bm", "CcspPandMSsp", "meshAgent", "webconfig", "snmpd"]
    for process in processes:
        cpu_key = f"cpu_{process}"
        mem_key = f"mem_{process}"
        cpu_value = generate_random_value(config['ProcessCPU_range'], device_type)
        mem_value = generate_random_value(config['ProcessMem_range'], device_type)
        data.append({cpu_key: f"{cpu_value:.1f}"})
        data.append({mem_key: f"{int(mem_value)}"})


    return {"Report": data}

def initialize_devices(num_devices, normal_percent, medium_percent, extreme_percent):
    global generated_macs
    devices = []
    normal_count = math.floor(num_devices * normal_percent / 100)
    medium_count = math.floor(num_devices * medium_percent / 100)
    extreme_count = num_devices - normal_count - medium_count

    mac_addresses = generate_mac_sequence(num_devices)
    generated_macs = mac_addresses  # Store the generated MAC addresses

    for i in range(num_devices):
        device_type = "normal" if i < normal_count else ("medium" if i < normal_count + medium_count else "extreme")
        mac = mac_addresses[i]
        device = {
            "mac": mac,
            "CMMAC": generate_cmmac(mac),
            "CMTSMAC": "00:90:F0:55:02:00",
            "SoftwareVersion": f"CGM4981COM_{random.randint(1, 10)}.{random.randint(0, 9)}p{random.randint(1, 5)}s{random.randint(1, 3)}_PROD_sey",
            "WAN_IP": generate_ipv4(),
            "type": device_type
        }
        devices.append(device)

    random.shuffle(devices)
    return devices

def send_to_api(data, endpoint):
    try:
        response = requests.post(endpoint, json=data)
        print("---------------- Success ----------")
        return response.status_code == 200
    except requests.RequestException:
        print("---------------- error Occured ----------")
        return False

def generate_telemetry_files(num_devices, duration, interval, normal_percent, medium_percent, extreme_percent, config, endpoint, time_gap):
    global generated_files
    generated_files = []
    devices = initialize_devices(num_devices, normal_percent, medium_percent, extreme_percent)
    start_time = datetime.datetime.now(datetime.timezone.utc)
    iteration = 0

    if not os.path.exists("telemetry_output"):
        os.makedirs("telemetry_output")

    while not stop_generation.is_set() and (datetime.datetime.now(datetime.timezone.utc) - start_time).total_seconds() < duration:
        current_time = datetime.datetime.now(datetime.timezone.utc)
        
        for i, device in enumerate(devices):
            telemetry_data = generate_telemetry_data(device, current_time, config)
            
            safe_mac = device['mac'].replace(':', '_')
            filename = f"telemetry_output/cpe_telemetry_{safe_mac}_{current_time.strftime('%Y%m%d_%H%M%S')}_UTC.json"
            with open(filename, 'w') as f:
                json.dump(telemetry_data, f, indent=2)

            generated_files.append(filename)

            if endpoint:
                send_to_api(telemetry_data, endpoint)

            if i < len(devices) - 1:  # Don't sleep after the last device
                time.sleep(time_gap)

        iteration += 1
        time_elapsed = (datetime.datetime.now(datetime.timezone.utc) - current_time).total_seconds()
        sleep_time = max(0, interval - time_elapsed)
        time.sleep(sleep_time)

    return iteration

@app.route('/')
def index():
    return render_template('index.html', config=default_config)

@app.route('/generate', methods=['POST'])
def generate():
    global telemetry_thread, stop_generation, generated_files

    if telemetry_thread and telemetry_thread.is_alive():
        return jsonify({"error": "Generation is already in progress"}), 400

    num_devices = int(request.form['num_devices'])
    duration = int(request.form['duration'])
    interval = float(request.form['interval'])
    normal_percent = float(request.form['normal_percent'])
    medium_percent = float(request.form['medium_percent'])
    extreme_percent = float(request.form['extreme_percent'])
    endpoint = request.form.get('endpoint', '')
    time_gap = float(request.form['time_gap'])

    if interval <= num_devices * time_gap:
        return jsonify({"error": "Interval must be greater than (number of devices * time gap)"}), 400

    config = {}
    for key, value in request.form.items():
        if key.endswith('_range'):
            ranges = json.loads(value)
            config[key] = {
                "normal": tuple(map(float, ranges["normal"].split(','))),
                "medium": tuple(map(float, ranges["medium"].split(','))),
                "extreme": tuple(map(float, ranges["extreme"].split(',')))
            }

    stop_generation.clear()
    telemetry_thread = threading.Thread(target=generate_telemetry_files, 
                                        args=(num_devices, duration, interval, normal_percent, medium_percent, extreme_percent, config, endpoint, time_gap))
    telemetry_thread.start()

    return jsonify({"message": "Telemetry generation started"}), 200

@app.route('/stop')
def stop():
    global stop_generation
    stop_generation.set()
    return jsonify({"message": "Telemetry generation stopped"}), 200

@app.route('/status')
def status():
    global telemetry_thread, generated_files, generated_macs
    if telemetry_thread and telemetry_thread.is_alive():
        return jsonify({"status": "running", "files": generated_files, "macs": generated_macs}), 200
    else:
        return jsonify({"status": "stopped", "files": generated_files, "macs": generated_macs}), 200
  
@app.route('/download/<filename>')
def download_file(filename):
    file_path = os.path.join('telemetry_output', filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    else:
        return jsonify({"error": "File not found"}), 404
    
@app.route('/clear', methods=['POST'])
def clear_telemetry():
    global generated_files, generated_macs
    try:
        # Clear the telemetry_output directory
        shutil.rmtree('telemetry_output')
        os.makedirs('telemetry_output')
        
        # Clear the global variables
        generated_files = []
        generated_macs = []
        
        return jsonify({"message": "All telemetry outputs cleared successfully"}), 200
    except Exception as e:
        return jsonify({"error": f"Failed to clear telemetry outputs: {str(e)}"}), 500

# ---------------- LOCAL ------------------
# if __name__ == '__main__':
#     app.run(debug=True)

# ---------------- RENDER ------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)