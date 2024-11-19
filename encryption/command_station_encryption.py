import socket
import json
import logging
import threading
import time
import sys
from encryption_util import decrypt_message
 
# Configuration
COMMAND_STATION_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 33500
METRICS_UPDATE_INTERVAL = 30  # Interval for displaying metrics
 
# Metrics tracking
metrics = {
    "total_messages_received": 0,
    "control_messages_received": 0,
    "data_messages_received": 0,
    "unknown_messages_received": 0,
    "malformed_messages_received": 0,
    "average_processing_time": 0,
    "sources": {},
}
metrics_lock = threading.Lock()
 
# Logging Configuration
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S"
)
 
def update_metric(key, increment=1):
    """Thread-safe metric update."""
    with metrics_lock:
        if key in metrics:
            metrics[key] += increment
 
def log_message(level, message):
    """Centralized logging function."""
    log_function = {
        "info": logging.info,
        "warning": logging.warning,
        "error": logging.error,
    }.get(level.lower(), logging.info)
    log_function(message)
 
def process_message(encrypted_message, addr):
    """Processes incoming encrypted messages."""
    start_time = time.time()
    try:
        message = json.loads(decrypt_message(encrypted_message))
        source = message.get("source", "unknown")
        message_type = message.get("type", "unknown")
        with metrics_lock:
            if source not in metrics["sources"]:
                metrics["sources"][source] = 0
            metrics["sources"][source] += 1
 
        # Process message
        if message_type == "control":
            log_message("info", f"[Control Message from {addr}] {json.dumps(message, indent=2)}")
            update_metric("control_messages_received")
        elif message_type == "data":
            log_message("info", f"[Data Message from {addr}] {json.dumps(message, indent=2)}")
            update_metric("data_messages_received")
        else:
            log_message("warning", f"[Unknown Message from {addr}] {json.dumps(message, indent=2)}")
            update_metric("unknown_messages_received")
 
    except Exception as e:
        log_message("error", f"Error processing message: {e}")
        update_metric("malformed_messages_received")
    finally:
        with metrics_lock:
            processing_time = time.time() - start_time
            metrics["total_messages_received"] += 1
            metrics["average_processing_time"] = (
                (metrics["average_processing_time"] + processing_time) / 2
            )
 
def display_metrics():
    """Periodically display metrics."""
    while True:
        time.sleep(METRICS_UPDATE_INTERVAL)
        with metrics_lock:
            logging.info(f"Metrics: {json.dumps(metrics, indent=2)}")
 
def main():
    """Main function for the Command Station."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("", COMMAND_STATION_PORT))
        log_message("info", f"Command Station listening on port {COMMAND_STATION_PORT}...")
    except OSError as e:
        log_message("error", f"Failed to bind to port {COMMAND_STATION_PORT}: {e}")
        return
 
    threading.Thread(target=display_metrics, daemon=True).start()
 
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            process_message(data.decode(), addr)
        except Exception as e:
            log_message("error", f"Error receiving data: {e}")
 
if __name__ == "__main__":
    main()
