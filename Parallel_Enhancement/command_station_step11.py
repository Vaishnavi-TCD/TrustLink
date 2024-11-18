import socket
import json
 
# Configuration
COMMAND_STATION_PORT = 33500
 
 
def process_message(message):
    """
    Processes incoming messages, differentiating control and data types.
    """
    if message["type"] == "control":
        print(f"[Control Message] {json.dumps(message, indent=2)}")
    elif message["type"] == "data":
        print(f"[Data Message] {json.dumps(message, indent=2)}")
    else:
        print(f"[Unknown Message Type] {json.dumps(message, indent=2)}")
 
 
def main():
    """Command Station main function."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", COMMAND_STATION_PORT))
    print(f"Command Station listening on port {COMMAND_STATION_PORT}...")
 
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            message = json.loads(data.decode())
            print(f"Received from {addr}:")
            process_message(message)
        except Exception as e:
            print(f"Error in Command Station: {e}")
 
 
if __name__ == "__main__":
    main()

