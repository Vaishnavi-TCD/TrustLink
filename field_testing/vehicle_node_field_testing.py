import socket
import json
import time
import random
import threading
import logging

# Configuration
BROADCAST_PORT = 34000
ACK_LISTEN_PORT = 33020
SATELLITE_DISCOVERY_TIMEOUT = 10  # Timeout for satellite discovery
DATA_SEND_INTERVAL = 5  # Interval between data transmissions
MAX_RETRIES = 3  # Maximum number of retries for sending data
ACK_TIMEOUT = 2  # Timeout for waiting for an ACK
SATELLITE_REDISCOVERY_INTERVAL = 60  # Rediscovery interval for satellites
PACKET_LOSS_PROBABILITY = 0.1  # 10% chance of packet loss
BANDWIDTH_LIMIT = 5000  # Bandwidth limit in bytes per second

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

# Logging Configuration
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S"
)


def create_message(msg_type, source, destination, payload=None):
    """Create a formatted message."""
    return json.dumps({
        "type": msg_type,
        "source": source,
        "destination": destination,
        "payload": payload,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "id": "%s-%d" % (source, int(time.time() * 1000000))  # Unique ID for the message using microseconds
    })


def simulate_packet_loss():
    """Simulate packet loss based on probability."""
    return random.random() < PACKET_LOSS_PROBABILITY


def simulate_bandwidth(data):
    """Simulate bandwidth constraints."""
    data_size = len(data.encode("utf-8"))  # Size in bytes
    delay = float(data_size) / BANDWIDTH_LIMIT  # Simulated delay
    time.sleep(delay)


def discover_satellites():
    """Discover satellites via broadcast."""
    discovered = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", BROADCAST_PORT))
    sock.settimeout(1)  # Short timeout for each listen cycle
    logging.info("Listening for satellite broadcasts...")

    start_time = time.time()
    while time.time() - start_time < SATELLITE_DISCOVERY_TIMEOUT:
        try:
            data, addr = sock.recvfrom(1024)
            message = json.loads(data)
            if message["type"] == "announcement" and "port" in message["payload"]:
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


def send_data(sock, satellite_ip, satellite_port, message):
    """Send data to a satellite and wait for acknowledgment."""
    for attempt in range(MAX_RETRIES):
        try:
            if simulate_packet_loss():
                logging.warning("Simulated packet loss during transmission to %s:%s." % (satellite_ip, satellite_port))
                continue

            start_time = time.time()
            simulate_bandwidth(message)  # Simulate bandwidth constraints
            sock.sendto(message.encode("utf-8"), (satellite_ip, satellite_port))
            logging.info("Sent data to %s:%s: %s" % (satellite_ip, satellite_port, message))
            with metrics_lock:
                metrics["total_messages_sent"] += 1

            # Wait for acknowledgment
            sock.settimeout(ACK_TIMEOUT)
            logging.info("Waiting for ACK on port %s..." % ACK_LISTEN_PORT)
            ack, addr = sock.recvfrom(1024)
            ack_message = json.loads(ack)
            logging.info("Received ACK from %s: %s" % (addr, ack_message))

            if ack_message["type"] == "ack" and ack_message["source"].startswith("satellite"):
                with metrics_lock:
                    metrics["successful_transmissions"] += 1
                    response_time = time.time() - start_time
                    metrics["average_response_time"] = (
                        (metrics["average_response_time"] + response_time) / 2
                    )
                logging.info("ACK validated from Satellite %s." % ack_message["source"])
                return True
        except socket.timeout:
            logging.warning("No ACK received from %s:%s, attempt %d/%d." % (
                satellite_ip, satellite_port, attempt + 1, MAX_RETRIES))
            with metrics_lock:
                metrics["retransmissions"] += 1
            time.sleep(2 ** attempt)  # Exponential backoff
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
    while True:
        time.sleep(SATELLITE_REDISCOVERY_INTERVAL)
        logging.info("Rediscovering satellites...")
        new_satellites = discover_satellites()
        satellites.update(new_satellites)
        logging.info("Updated Satellite List: %s" % satellites)


def display_metrics():
    """Display metrics periodically."""
    while True:
        time.sleep(30)
        with metrics_lock:
            logging.info("Metrics: %s" % metrics)


def main():
    """Main vehicle node function."""
    satellites = discover_satellites()

    if not satellites:
        logging.error("No satellites discovered. Exiting...")
        return

    # Start a background thread for periodic rediscovery
    rediscovery_thread = threading.Thread(target=rediscover_satellites, args=(satellites,))
    rediscovery_thread.setDaemon(True)
    rediscovery_thread.start()

    # Start a thread for displaying metrics
    metrics_thread = threading.Thread(target=display_metrics)
    metrics_thread.setDaemon(True)
    metrics_thread.start()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", ACK_LISTEN_PORT))
    logging.info("Listening for ACKs on port %s." % ACK_LISTEN_PORT)

    try:
        while True:
            vehicle_id = generate_vehicle_id()
            gps_data = generate_gps_data()

            logging.info("Generated new data - Vehicle ID: %s, GPS: %s" % (vehicle_id, gps_data))

            message = create_message("data", vehicle_id, "satellite", {"gps": gps_data})

            for satellite, details in satellites.items():
                logging.info("Attempting to send data to Satellite %s at %s:%s" % (
                    satellite, details["ip"], details["port"]))
                success = send_data(sock, details["ip"], details["port"], message)

                if success:
                    logging.info("Data successfully transmitted and acknowledged by Satellite %s." % satellite)
                    break
                else:
                    logging.warning("Failed to send data to Satellite %s after %d retries." % (
                        satellite, MAX_RETRIES))

            logging.info("Waiting for %d seconds before sending the next data packet..." % DATA_SEND_INTERVAL)
            time.sleep(DATA_SEND_INTERVAL)
    finally:
        sock.close()


if __name__ == "__main__":
    random.seed()
    main()
