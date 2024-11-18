import socket
import json
import time
import random
import threading
import logging
import queue
import sys
 
# Configuration
SATELLITE_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 33001
BROADCAST_PORT = 34000
COMMAND_STATION_IP = "10.35.70.19"  # Replace with actual Command Station IP
COMMAND_STATION_PORT = 33500
BROADCAST_INTERVAL = 5  # Interval between broadcast announcements (seconds)
ACK_LISTEN_PORT = 33020  # Port for receiving ACKs
MAX_CONNECTIONS = 5  # Max simultaneous connection handlers
ISL_DELAY = 0.2  # Inter-Satellite Link delay (seconds)
PACKET_LOSS_PROBABILITY = 0.1  # Simulated 10% chance of packet loss
BANDWIDTH_LIMIT = 5000  # Bandwidth limit in bytes/second
MAX_RETRIES = 3  # Max retries for packet forwarding
 
# Metrics
metrics = {
    "total_packets_received": 0,
    "total_packets_forwarded": 0,
    "total_packets_dropped": 0,
    "total_acks_sent": 0,
    "average_processing_time": 0,
    "duplicate_messages": 0,
    "shortest_path_updates": 0,
}
metrics_lock = threading.Lock()
 
# Logging Configuration
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S"
)
 
# Static Routing Table Fallback
ROUTING_TABLE = {
    "command_station": {"next_hop": "command_station", "ip": COMMAND_STATION_IP, "port": COMMAND_STATION_PORT},
    "sat_1": {"next_hop": "sat_2"},
    "sat_2": {"next_hop": "sat_3"},
    "sat_3": {"next_hop": "sat_4"},
    "sat_4": {"next_hop": "sat_5"},
    "sat_5": {"next_hop": "command_station"},
    "satellite": {"next_hop": "command_station"},
}
 
recent_messages = {}
connection_queue = queue.Queue()
 
# Utility Functions
def is_duplicate(message_id):
    """Check if a message ID has already been processed."""
    current_time = time.time()
    if message_id in recent_messages:
        if current_time - recent_messages[message_id] < 10:  # 10-second threshold
            with metrics_lock:
                metrics["duplicate_messages"] += 1
            return True
        else:
            del recent_messages[message_id]
    recent_messages[message_id] = current_time
    return False
 
def create_message(msg_type, source, destination, payload=None):
    """Create a formatted message."""
    return json.dumps({
        "type": msg_type,
        "source": source,
        "destination": destination,
        "payload": payload,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "id": f"{source}-{time.time_ns()}"
    })
 
def simulate_packet_loss():
    """Simulate packet loss based on probability."""
    return random.random() < PACKET_LOSS_PROBABILITY
 
def simulate_bandwidth(data):
    """Simulate bandwidth constraints."""
    data_size = len(data.encode("utf-8"))  # Size in bytes
    delay = data_size / BANDWIDTH_LIMIT  # Simulated delay
    time.sleep(delay)
 
# Satellite Functions
def broadcast_presence():
    """Broadcast satellite availability."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    broadcast_address = "255.255.255.255"
    while True:
        try:
            message = create_message(
                "announcement", f"satellite_{SATELLITE_PORT}", "all", {"port": SATELLITE_PORT}
            )
            if not simulate_packet_loss():
                simulate_bandwidth(message)
                sock.sendto(message.encode(), (broadcast_address, BROADCAST_PORT))
                logging.info(f"Broadcasted: {message}")
            else:
                with metrics_lock:
                    metrics["total_packets_dropped"] += 1
                logging.warning(f"Packet dropped during broadcast: {message}")
            time.sleep(BROADCAST_INTERVAL)
        except Exception as e:
            logging.error(f"Error broadcasting presence: {e}")
 
def send_ack(sock, addr, source):
    """Send acknowledgment to the sender."""
    ack_message = create_message("ack", f"satellite_{SATELLITE_PORT}", source, {"status": "received"})
    sock.sendto(ack_message.encode(), (addr[0], ACK_LISTEN_PORT))
    with metrics_lock:
        metrics["total_acks_sent"] += 1
    logging.info(f"Sent ACK to source {source} at {addr[0]}:{ACK_LISTEN_PORT}")
 
def display_metrics():
    """Display metrics periodically."""
    while True:
        time.sleep(30)
        with metrics_lock:
            logging.info(f"Metrics for Satellite {SATELLITE_PORT}: {metrics}")
 
def get_next_hop(destination):
    """Determine the next hop for a given destination."""
    if destination in ROUTING_TABLE:
        entry = ROUTING_TABLE[destination]
        if "ip" in entry and "port" in entry:
            return entry  # Valid next hop with IP and port
        # Fallback to next_hop if direct entry is incomplete
        static_next_hop = entry.get("next_hop")
        if static_next_hop and static_next_hop in ROUTING_TABLE:
            next_hop_entry = ROUTING_TABLE[static_next_hop]
            if "ip" in next_hop_entry and "port" in next_hop_entry:
                return next_hop_entry
    logging.error(f"No valid next hop for destination: {destination}. Current routing table: {ROUTING_TABLE}")
    return None
 
def update_routing_table(message, addr):
    """Update the routing table based on announcements."""
    source = message["source"]
    payload = message["payload"]
    if "port" in payload:
        with metrics_lock:
            # Add or update the routing table entry
            ROUTING_TABLE[source] = {"ip": addr[0], "port": payload["port"]}
            metrics["shortest_path_updates"] += 1
        logging.info(f"Routing table updated: {ROUTING_TABLE}")
 
def forward_message(message):
    """Forward message based on routing table."""
    destination = message["destination"]
    next_hop = get_next_hop(destination)
    if next_hop:
        forward_to_neighbor(json.dumps(message), next_hop["ip"], next_hop["port"])
    else:
        logging.error(f"No route to destination {destination}. Routing table: {ROUTING_TABLE}")
        with metrics_lock:
            metrics["total_packets_dropped"] += 1
 
def forward_to_neighbor(data, ip, port):
    """Forward message to a specific neighbor."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for attempt in range(MAX_RETRIES):
        try:
            simulate_bandwidth(data)
            time.sleep(ISL_DELAY)
            sock.sendto(data.encode(), (ip, port))
            logging.info(f"Forwarded to neighbor at {ip}:{port}")
            with metrics_lock:
                metrics["total_packets_forwarded"] += 1
            return
        except Exception as e:
            logging.error(f"Retry {attempt + 1}: Error forwarding to neighbor {ip}:{port}: {e}")
            time.sleep(0.5)
    with metrics_lock:
        metrics["total_packets_dropped"] += 1
    logging.error(f"Failed to forward to neighbor {ip}:{port} after retries.")
 
def handle_connection(sock, addr, message):
    """Handle an individual connection."""
    try:
        start_time = time.time()
        logging.info(f"Handling message: {message}")
        if is_duplicate(message["id"]):
            logging.warning(f"Duplicate message detected: {message['id']}")
            return
        if message["type"] == "data":
            forward_message(message)
            send_ack(sock, addr, message["source"])
        elif message["type"] == "announcement":
            update_routing_table(message, addr)
        with metrics_lock:
            processing_time = time.time() - start_time
            metrics["total_packets_received"] += 1
            metrics["average_processing_time"] = (
                (metrics["average_processing_time"] + processing_time) / 2
            )
    except Exception as e:
        logging.error(f"Error handling connection: {e}")
 
# Add to the existing main and worker logic
def connection_worker(sock):
    """Worker thread to handle queued connections."""
    while True:
        try:
            addr, message = connection_queue.get()
            handle_connection(sock, addr, message)
            connection_queue.task_done()
        except Exception as e:
            logging.error(f"Error in connection worker: {e}")
 
def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("", SATELLITE_PORT))
        logging.info(f"Satellite {SATELLITE_PORT} listening on port {SATELLITE_PORT}.")
    except OSError as e:
        logging.error(f"Failed to bind to port {SATELLITE_PORT}: {e}")
        sys.exit(1)
    for _ in range(MAX_CONNECTIONS):
        threading.Thread(target=connection_worker, args=(sock,), daemon=True).start()
    threading.Thread(target=broadcast_presence, daemon=True).start()
    threading.Thread(target=display_metrics, daemon=True).start()
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            message = json.loads(data.decode())
            logging.info(f"Received data from {addr}: {message}")
            connection_queue.put((addr, message))
        except Exception as e:
            logging.error(f"Error on Satellite Node {SATELLITE_PORT}: {e}") 
if __name__ == "__main__":
    main()

