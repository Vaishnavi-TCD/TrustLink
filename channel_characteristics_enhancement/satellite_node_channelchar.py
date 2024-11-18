import socket
import json
import time
import threading
import sys
import queue
import random
 
# Configuration
SATELLITE_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 33001
BROADCAST_PORT = 34000
COMMAND_STATION_IP = "10.35.70.19"  # Replace with actual Command Station IP
COMMAND_STATION_PORT = 33500
BROADCAST_INTERVAL = 5
ACK_LISTEN_PORT = 33020  # Vehicle's designated ACK port
MAX_CONNECTIONS = 5  # Maximum simultaneous connections
ISL_DELAY = 0.2  # Simulated delay for inter-satellite links (in seconds)
PACKET_LOSS_PROBABILITY = 0.1  # 10% packet loss
BANDWIDTH_LIMIT = 5000  # Bandwidth limit in bytes per second
 
# Metrics
metrics = {
    "total_packets_received": 0,
    "total_packets_forwarded": 0,
    "total_packets_dropped": 0,
    "total_acks_sent": 0,
}
metrics_lock = threading.Lock()
 
# Routing Table and Neighbors
ROUTING_TABLE = {
    "command_station": {"next_hop": "command_station"},  # Direct to Command Station
    "sat_1": {"next_hop": "sat_2"},
    "sat_2": {"next_hop": "sat_3"},
    "sat_3": {"next_hop": "sat_4"},
    "sat_4": {"next_hop": "sat_5"},
    "sat_5": {"next_hop": "command_station"},
    "satellite": {"next_hop": "command_station"},  # Fallback for generic "satellite" destination
}
 
NEIGHBORS = [
    {"id": "command_station", "ip": "10.35.70.19", "port": 33500},
    {"id": "sat_1", "ip": "127.0.0.1", "port": 33001},
    {"id": "sat_2", "ip": "127.0.0.1", "port": 33002},
    {"id": "sat_3", "ip": "127.0.0.1", "port": 33003},
    {"id": "sat_4", "ip": "127.0.0.1", "port": 33004},
    {"id": "sat_5", "ip": "127.0.0.1", "port": 33005},
]
 
# Track processed message IDs to prevent duplication
recent_messages = {}
message_queue = queue.PriorityQueue()
connection_queue = queue.Queue()
 
def is_duplicate(message_id):
    """Check if a message ID has already been processed."""
    current_time = time.time()
    if message_id in recent_messages:
        if current_time - recent_messages[message_id] < 10:  # 10 seconds threshold
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
        "id": f"{source}-{time.time_ns()}"  # Unique message ID
    })
 
def simulate_packet_loss():
    """Simulate packet loss based on probability."""
    return random.random() < PACKET_LOSS_PROBABILITY
 
def simulate_bandwidth(data):
    """Simulate bandwidth constraints."""
    data_size = len(data.encode())  # Size in bytes
    delay = data_size / BANDWIDTH_LIMIT  # Simulated delay based on bandwidth
    time.sleep(delay)
 
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
                print(f"Satellite {SATELLITE_PORT} broadcasted: {message}")
            else:
                with metrics_lock:
                    metrics["total_packets_dropped"] += 1
                print(f"Packet dropped during broadcast: {message}")
            time.sleep(BROADCAST_INTERVAL)
        except Exception as e:
            print(f"Error broadcasting presence: {e}")
 
def forward_to_command_station(data):
    """Forward data to the Command Station."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        simulate_bandwidth(data)
        sock.sendto(data.encode(), (COMMAND_STATION_IP, COMMAND_STATION_PORT))
        print(f"Satellite {SATELLITE_PORT} forwarded data to Command Station.")
        with metrics_lock:
            metrics["total_packets_forwarded"] += 1
    except Exception as e:
        print(f"Error forwarding to Command Station: {e}")
    finally:
        sock.close()
 
def forward_to_neighbor(message, neighbor):
    """Forward data to a specific neighboring satellite."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        time.sleep(ISL_DELAY)
        if not simulate_packet_loss():
            simulate_bandwidth(message)
            sock.sendto(message.encode(), (neighbor["ip"], neighbor["port"]))
            print(f"Forwarded data to neighbor {neighbor['id']} at {neighbor['ip']}:{neighbor['port']}")
            with metrics_lock:
                metrics["total_packets_forwarded"] += 1
        else:
            with metrics_lock:
                metrics["total_packets_dropped"] += 1
            print(f"Packet dropped during forwarding: {message}")
    except Exception as e:
        print(f"Error forwarding to neighbor {neighbor['id']}: {e}")
    finally:
        sock.close()
 
def route_data(message, neighbors):
    """Route data based on the routing table."""
    priority = message.get("priority", 1)
    message_queue.put((priority, message))
    while not message_queue.empty():
        _, msg = message_queue.get()
        destination = msg["destination"]
 
        if is_duplicate(msg["id"]):
            continue
 
        try:
            if destination in ROUTING_TABLE:
                next_hop = ROUTING_TABLE[destination]["next_hop"]
                if next_hop == "command_station":
                    forward_to_command_station(json.dumps(msg))
                else:
                    neighbor = next((n for n in neighbors if n["id"] == next_hop), None)
                    if neighbor:
                        forward_to_neighbor(json.dumps(msg), neighbor)
                    else:
                        print(f"Error: No route to next hop {next_hop}.")
            else:
                print(f"Warning: No route for destination '{destination}'. Forwarding to command station.")
                forward_to_command_station(json.dumps(msg))
        except Exception as e:
            print(f"Error routing message: {e}")
 
def respond_to_vehicle(addr, vehicle_id):
    """Send acknowledgment to the vehicle."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        ack_message = create_message("ack", f"satellite_{SATELLITE_PORT}", vehicle_id, {"status": "received"})
        vehicle_ip = addr[0]
        sock.sendto(ack_message.encode(), (vehicle_ip, ACK_LISTEN_PORT))
        with metrics_lock:
            metrics["total_acks_sent"] += 1
        print(f"Sent ACK to Vehicle {vehicle_id} at {vehicle_ip}:{ACK_LISTEN_PORT}")
    except Exception as e:
        print(f"Error sending ACK to Vehicle: {e}")
    finally:
        sock.close()
 
def handle_connection(sock, addr, message):
    """Handle an individual connection."""
    try:
        if message["type"] == "data":
            print(f"Routing data: {message}")
            route_data(message, NEIGHBORS)
            respond_to_vehicle(addr, message["source"])
    except Exception as e:
        print(f"Error handling connection: {e}")
 
def connection_worker(sock):
    """Worker thread to handle queued connections."""
    while True:
        try:
            addr, message = connection_queue.get()
            handle_connection(sock, addr, message)
            connection_queue.task_done()
        except Exception as e:
            print(f"Error in connection worker: {e}")
 
def display_metrics():
    """Display metrics periodically."""
    while True:
        time.sleep(30)
        with metrics_lock:
            print(f"Metrics for Satellite {SATELLITE_PORT}: {metrics}")
 
def main():
    """Main satellite node function."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("", SATELLITE_PORT))
        print(f"Satellite {SATELLITE_PORT} listening on port {SATELLITE_PORT}.")
    except OSError as e:
        print(f"Failed to bind to port {SATELLITE_PORT}: {e}")
        sys.exit(1)
 
    for _ in range(MAX_CONNECTIONS):
        threading.Thread(target=connection_worker, args=(sock,), daemon=True).start()
 
    threading.Thread(target=broadcast_presence, daemon=True).start()
    threading.Thread(target=display_metrics, daemon=True).start()
 
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            message = json.loads(data.decode())
            print(f"Satellite {SATELLITE_PORT} received data from {addr}: {message}")
            connection_queue.put((addr, message))
        except Exception as e:
            print(f"Error on Satellite Node {SATELLITE_PORT}: {e}")
 
if __name__ == "__main__":
    main()