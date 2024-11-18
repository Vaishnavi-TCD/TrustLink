import socket
import json
import time
import random
import threading
import logging
import signal
import sys

# Configuration
BROADCAST_PORT = 34000
ACK_LISTEN_PORT = 33020
SATELLITE_DISCOVERY_TIMEOUT = 10
DATA_SEND_INTERVAL = 5
MAX_RETRIES = 3
ACK_TIMEOUT = 2
SATELLITE_REDISCOVERY_INTERVAL = 60
PACKET_LOSS_PROBABILITY = 0.05  # Reduced for debugging
BANDWIDTH_LIMIT = 5000

# Metrics tracking
metrics = {
    "total_messages_sent": 0,
    "successful_transmissions": 0,
    "retransmissions": 0,
    "failed_transmissions": 0,
    "average_response_time": 0,
    "discovered_satellites": 0,
}

# Thread-safe lock for metrics
metrics_lock = threading.Lock()

# Shutdown flag
shutdown_flag = threading.Event()

# Logging Configuration
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S"
)


def signal_handler(sig, frame):
    """Handles shutdown signals to terminate gracefully."""
    logging.info("Shutting down vehicle node...")
    shutdown_flag.set()
    sys.exit(0)

def create_message(msg_type, source, destination, payload=None):
    """Create a formatted message."""
    return json.dumps({
        "type": msg_type,
        "source": source,
        "destination": destination,
        "payload": payload,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "id": "%s-%d" % (source, int(time.time() * 1000000))
    })


def simulate_packet_loss():
    """Simulate packet loss based on probability."""
    return random.random() < PACKET_LOSS_PROBABILITY


def simulate_bandwidth(data):
    """Simulate bandwidth constraints."""
    data_size = len(data.encode("utf-8"))
    delay = float(data_size) / BANDWIDTH_LIMIT
    time.sleep(delay)


def discover_satellites():
    """Discover satellites via broadcast."""
    discovered = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", BROADCAST_PORT))
    sock.settimeout(1)
    logging.info("Listening for satellite broadcasts...")

    start_time = time.time()
    with metrics_lock:
        metrics["discovered_satellites"] = 0

    while time.time() - start_time < SATELLITE_DISCOVERY_TIMEOUT:
        try:
            data, addr = sock.recvfrom(1024)
            message = json.loads(data)
            if message.get("type") == "announcement" and "port" in message["payload"]:
                discovered[message["source"]] = {"ip": addr[0], "port": message["payload"]["port"]}
                logging.info("Discovered Satellite %s on IP %s Port %s" % (
                    message["source"], addr[0], message["payload"]["port"]))
                with metrics_lock:
                    metrics["discovered_satellites"] += 1
        except socket.timeout:
            continue
        except Exception as e:
            logging.error("Error during satellite discovery: %s" % e)
    sock.close()
    return discovered
def select_best_satellite(satellites):
    """Select the best satellite based on random or specific criteria."""
    if not satellites:
        logging.error("No satellites available for selection.")
        return None
    selected = random.choice(list(satellites.values()))
    logging.info("Selected Satellite IP: %s, Port: %s" % (selected["ip"], selected["port"]))
    return selected


def send_data(sock, satellite_ip, satellite_port, message):
    """Send data to a satellite and wait for acknowledgment."""
    for attempt in range(MAX_RETRIES):
        try:
            if simulate_packet_loss():
                logging.warning("Simulated packet loss during transmission to %s:%s." % (satellite_ip, satellite_port))
                continue

            start_time = time.time()
            simulate_bandwidth(message)
            sock.sendto(message.encode("utf-8"), (satellite_ip, satellite_port))
            logging.info("Sent data to %s:%s: %s" % (satellite_ip, satellite_port, message))
            with metrics_lock:
                metrics["total_messages_sent"] += 1

            sock.settimeout(ACK_TIMEOUT)
            ack, addr = sock.recvfrom(1024)
            ack_message = json.loads(ack)

            if ack_message.get("type") == "ack":
                response_time = time.time() - start_time
                with metrics_lock:
                    metrics["successful_transmissions"] += 1
                    metrics["average_response_time"] = (
                        (metrics["average_response_time"] + response_time) / 2
                    )
                logging.info("ACK received from Satellite %s." % ack_message["source"])
                return True
        except socket.timeout:
            logging.warning("No ACK received from %s:%s, attempt %d/%d." % (
                satellite_ip, satellite_port, attempt + 1, MAX_RETRIES))
            with metrics_lock:
                metrics["retransmissions"] += 1
        except Exception as e:
            logging.error("Error during ACK handling: %s" % e)

    with metrics_lock:
        metrics["failed_transmissions"] += 1
    return False
def generate_gps_data():
    """Generate random GPS data."""
    latitude = random.uniform(-90, 90)
    longitude = random.uniform(-180, 180)
    logging.info("Generated GPS data: Latitude=%s, Longitude=%s" % (latitude, longitude))
    return {"latitude": latitude, "longitude": longitude}


def generate_vehicle_id():
    """Generate a random vehicle ID."""
    vehicle_id = "vehicle_%d" % random.randint(1000, 9999)
    logging.info("Generated Vehicle ID: %s" % vehicle_id)
    return vehicle_id


def rediscover_satellites(satellites):
    """Periodically rediscover satellites."""
    while not shutdown_flag.is_set():
        time.sleep(SATELLITE_REDISCOVERY_INTERVAL)
        logging.info("Rediscovering satellites...")
        new_satellites = discover_satellites()
        satellites.update(new_satellites)
        logging.info("Updated Satellite List: %s" % satellites)


def display_metrics():
    """Display metrics periodically."""
    while not shutdown_flag.is_set():
        time.sleep(30)
        with metrics_lock:
            logging.info("Metrics: %s" % metrics)
def main():
    """Main vehicle node function."""
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    satellites = discover_satellites()
    if not satellites:
        logging.error("No satellites discovered. Exiting...")
        return

    rediscovery_thread = threading.Thread(target=rediscover_satellites, args=(satellites,))
    rediscovery_thread.setDaemon(True)
    rediscovery_thread.start()

    metrics_thread = threading.Thread(target=display_metrics)
    metrics_thread.setDaemon(True)
    metrics_thread.start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", ACK_LISTEN_PORT))
    logging.info("Listening for ACKs on port %s." % ACK_LISTEN_PORT)

    try:
        while not shutdown_flag.is_set():
            vehicle_id = generate_vehicle_id()
            gps_data = generate_gps_data()
            message = create_message("data", vehicle_id, "satellite", {"gps": gps_data})

            selected_satellite = select_best_satellite(satellites)
            if selected_satellite:
                success = send_data(sock, selected_satellite["ip"], selected_satellite["port"], message)
                if success:
                    logging.info("Data successfully transmitted to Satellite %s." % selected_satellite["ip"])
                else:
                    logging.warning("Failed to transmit data.")
            time.sleep(DATA_SEND_INTERVAL)
    finally:
        sock.close()


if __name__ == "__main__":
    random.seed()
    main()

                                         