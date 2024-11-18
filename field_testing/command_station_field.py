import socket
import json
import logging
import threading
import time
 
# Configuration
COMMAND_STATION_PORT = 33500
METRICS_UPDATE_INTERVAL = 30  # Interval for displaying metrics
 
# Metrics tracking
metrics = {
    "total_messages_received": 0,
    "control_messages_received": 0,
    "data_messages_received": 0,
    "unknown_messages_received": 0,
    "average_processing_time": 0,
}
 
metrics_lock = threading.Lock()
 
# Logging Configuration
logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
 
 
def process_message(message):
    """
    Processes incoming messages, differentiating control and data types.
    Updates metrics accordingly.
    """
    start_time = time.time()
    try:
        if message["type"] == "control":
            logging.info(f"[Control Message] {json.dumps(message, indent=2)}")
            with metrics_lock:
                metrics["control_messages_received"] += 1
        elif message["type"] == "data":
            logging.info(f"[Data Message] {json.dumps(message, indent=2)}")
            with metrics_lock:
                metrics["data_messages_received"] += 1
        else:
            logging.warning(f"[Unknown Message Type] {json.dumps(message, indent=2)}")
            with metrics_lock:
                metrics["unknown_messages_received"] += 1
    except Exception as e:
        logging.error(f"Error processing message: {e}")
    finally:
        processing_time = time.time() - start_time
        with metrics_lock:
            metrics["total_messages_received"] += 1
            metrics["average_processing_time"] = (
                (metrics["average_processing_time"] + processing_time) / 2
                if metrics["total_messages_received"] > 1
                else processing_time
            )
 
 
def display_metrics():
    """
    Periodically display metrics to monitor the performance and received messages.
    """
    while True:
        time.sleep(METRICS_UPDATE_INTERVAL)
        with metrics_lock:
            logging.info(f"Metrics: {metrics}")
 
 
def main():
    """Command Station main function."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("", COMMAND_STATION_PORT))
        logging.info(f"Command Station listening on port {COMMAND_STATION_PORT}...")
    except OSError as e:
        logging.error(f"Failed to bind to port {COMMAND_STATION_PORT}: {e}")
        return
 
    # Start a thread to periodically display metrics
    threading.Thread(target=display_metrics, daemon=True).start()
 
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            message = json.loads(data.decode())
            logging.info(f"Received from {addr}: {message}")
            process_message(message)
        except json.JSONDecodeError:
            logging.warning("Received malformed JSON message.")
        except Exception as e:
            logging.error(f"Error in Command Station: {e}")
 
 
if __name__ == "__main__":
    main()