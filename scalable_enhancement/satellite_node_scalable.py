import socket
import json
import time
import threading
import sys
import queue
import random
import logging
 
# Configuration
SATELLITE_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 33001
BROADCAST_PORT = 34000
COMMAND_STATION_IP = "10.35.70.19"  # Replace with actual Command Station IP
COMMAND_STATION_PORT = 33500
BROADCAST_INTERVAL = 5  # Interval between broadcast announcements (seconds)
ACK_LISTEN_PORT = 33020  # Port for receiving ACKs
MAX_CONNECTIONS = 5  # Max simultaneous connection handlers
ISL_DELAY = 0.2  # Inter-Satellite Link delay (seconds)
PACKET_LOSS_PROBABILITY = 0.1  # 10% chance of packet loss
BANDWIDTH_LIMIT = 5000  # Bandwidth limit in bytes/second
MAX_RETRIES = 3  # Max retries for packet forwarding
PRIORITY_LEVELS = 5  # Levels of priority for handling messages
 
# Metrics
metrics = {
    "total_packets_received": 0,
    "total_packets_forwarded": 0,
    "total_packets_dropped": 0,
    "total_acks_sent": 0,
    "average_processing_time": 0,
}
metrics_lock = threading.Lock()
 
# Logging Configuration
logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
 
# Routing Table and Neighbors
ROUTING_TABLE = {
    "command_station": {"next_hop": "command_station"},
    "sat_1": {"next_hop": "sat_2"},
    "sat_2": {"next_hop": "sat_3"},
    "sat_3": {"next_hop": "sat_4"},
    "sat_4": {"next_hop": "sat_5"},
    "sat_5": {"next_hop": "command_station"},
    "satellite": {"next_hop": "command_station"},
}
 
NEIGHBORS = [
    {"id": "command_station", "ip": COMMAND_STATION_IP, "port": COMMAND_STATION_PORT},
    {"id": "sat_1", "ip": "127.0.0.1", "port": 33001},
    {"id": "sat_2", "ip": "127.0.0.1", "port": 33002},
    {"id": "sat_3", "ip": "127.0.0.1", "port": 33003},
    {"id": "sat_4", "ip": "127.0.0.1", "port": 33004},
    {"id": "sat_5", "ip": "127.0.0.1", "port": 33005},
]
 
# Message Tracking
recent_messages = {}
message_queue = queue.PriorityQueue()
connection_queue = queue.Queue()
 
 
# Utility Functions
def is_duplicate(message_id):
    """Check if a message ID has already been processed."""
    current_time = time.time()
    if message_id in recent_messages:
        if current_time - recent_messages[message_id] < 10:  # 10-second threshold
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
    data_size = len(data.encode())  # Size in bytes
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
 
 
def forward_to_command_station(data):
    """Forward data to the Command Station."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for attempt in range(MAX_RETRIES):
        try:
            simulate_bandwidth(data)
            sock.sendto(data.encode(), (COMMAND_STATION_IP, COMMAND_STATION_PORT))
            logging.info("Forwarded data to Command Station.")
            with metrics_lock:
                metrics["total_packets_forwarded"] += 1
            return
        except Exception as e:
            logging.error(f"Retry {attempt + 1}: Error forwarding to Command Station: {e}")
            time.sleep(0.5)
    with metrics_lock:
        metrics["total_packets_dropped"] += 1
    logging.error("Failed to forward to Command Station after retries.")
 
 
def forward_to_neighbor(message, neighbor):
    """Forward data to a specific neighboring satellite."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for attempt in range(MAX_RETRIES):
        try:
            simulate_bandwidth(message)
            time.sleep(ISL_DELAY)
            sock.sendto(message.encode(), (neighbor["ip"], neighbor["port"]))
            logging.info(f"Forwarded to neighbor {neighbor['id']} at {neighbor['ip']}:{neighbor['port']}")
            with metrics_lock:
                metrics["total_packets_forwarded"] += 1
            return
        except Exception as e:
            logging.error(f"Retry {attempt + 1}: Error forwarding to neighbor {neighbor['id']}: {e}")
            time.sleep(0.5)
    with metrics_lock:
        metrics["total_packets_dropped"] += 1
    logging.error(f"Failed to forward to neighbor {neighbor['id']} after retries.")
 
 
def route_data(message):
    """Route data based on the routing table."""
    destination = message["destination"]
 
    if is_duplicate(message["id"]):
        logging.warning(f"Duplicate message detected: {message['id']}")
        return
 
    try:
        if destination in ROUTING_TABLE:
            next_hop = ROUTING_TABLE[destination]["next_hop"]
            if next_hop == "command_station":
                forward_to_command_station(json.dumps(message))
            else:
                neighbor = next((n for n in NEIGHBORS if n["id"] == next_hop), None)
                if neighbor:
                    forward_to_neighbor(json.dumps(message), neighbor)
                else:
                    logging.error(f"No route to next hop {next_hop}.")
        else:
            logging.warning(f"No route for destination '{destination}'. Using fallback to command station.")
            forward_to_command_station(json.dumps(message))
    except Exception as e:
        logging.error(f"Error routing message: {e}")
 
 
def send_ack(sock, addr, vehicle_id):
    """Send acknowledgment to the vehicle."""
    ack_message = create_message("ack", f"satellite_{SATELLITE_PORT}", vehicle_id, {"status": "received"})
    sock.sendto(ack_message.encode(), (addr[0], ACK_LISTEN_PORT))
    with metrics_lock:
        metrics["total_acks_sent"] += 1
    logging.info(f"Sent ACK to Vehicle {vehicle_id} at {addr[0]}:{ACK_LISTEN_PORT}")
 
 
def handle_connection(sock, addr, message):
    """Handle an individual connection."""
    try:
        start_time = time.time()
        logging.info(f"Handling message: {message}")
        if message["type"] == "data":
            route_data(message)
            send_ack(sock, addr, message["source"])
        with metrics_lock:
            processing_time = time.time() - start_time
            metrics["average_processing_time"] = (
                (metrics["average_processing_time"] + processing_time) / 2
            )
    except Exception as e:
        logging.error(f"Error handling connection: {e}")
 
 
def connection_worker(sock):
    """Worker thread to handle queued connections."""
    while True:
        try:
            addr, message = connection_queue.get()
            handle_connection(sock, addr, message)
            connection_queue.task_done()
        except Exception as e:
            logging.error(f"Error in connection worker: {e}")
 
 
def display_metrics():
    """Display metrics periodically."""
    while True:
        time.sleep(30)
        with metrics_lock:
            logging.info(f"Metrics for Satellite {SATELLITE_PORT}: {metrics}")
 
 
# Main Function
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
    random.seed()
    main()
