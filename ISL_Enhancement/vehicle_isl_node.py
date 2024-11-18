import socket
import json
import time
import random

# Configuration
BROADCAST_PORT = 34000
ACK_LISTEN_PORT = 33020
SATELLITE_DISCOVERY_TIMEOUT = 10  # Timeout for satellite discovery
DATA_SEND_INTERVAL = 5  # Interval between data transmissions
MAX_RETRIES = 3  # Maximum number of retries for sending data
ACK_TIMEOUT = 2  # Timeout for waiting for an ACK


def create_message(msg_type, source, destination, payload=None):
    """Create a formatted message."""
    return json.dumps({
        "type": msg_type,
        "source": source,
        "destination": destination,
        "payload": payload,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "id": "{}-{}".format(source, int(time.time() * 1000000))  # Unique ID for the message using microseconds
    })


def discover_satellites():
    """Discover satellites via broadcast."""
    discovered = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", BROADCAST_PORT))
    sock.settimeout(1)  # Short timeout for each listen cycle
    print "Listening for satellite broadcasts..."

    start_time = time.time()
    while time.time() - start_time < SATELLITE_DISCOVERY_TIMEOUT:
        try:
            data, addr = sock.recvfrom(1024)
            message = json.loads(data)
            if message["type"] == "announcement" and "port" in message["payload"]:
                discovered[message["source"]] = {"ip": addr[0], "port": message["payload"]["port"]}
                print "Discovered Satellite {} on IP {} Port {}".format(message['source'], addr[0], message['payload']['port'])
        except socket.timeout:
            print "No broadcasts received during this interval."
            continue
        except Exception as e:
            print "Error during satellite discovery: {}".format(e)
    sock.close()
    return discovered


def send_data(sock, satellite_ip, satellite_port, message):
    """Send data to a satellite and wait for acknowledgment."""
    for attempt in range(MAX_RETRIES):
        try:
            sock.sendto(message, (satellite_ip, satellite_port))
            print "Sent data to {}:{}: {}".format(satellite_ip, satellite_port, message)

            # Wait for acknowledgment
            sock.settimeout(ACK_TIMEOUT)
            print "Waiting for ACK on port {}...".format(ACK_LISTEN_PORT)
            ack, addr = sock.recvfrom(1024)
            ack_message = json.loads(ack)
            print "Received ACK from {}: {}".format(addr, ack_message)

            if ack_message["type"] == "ack" and ack_message["source"].startswith("satellite"):
                print "ACK validated from Satellite {}.".format(ack_message['source'])
                return True
        except socket.timeout:
            print "No ACK received from Satellite {}:{}, attempt {}/{}.".format(satellite_ip, satellite_port, attempt + 1, MAX_RETRIES)
        except Exception as e:
            print "Error during ACK handling: {}".format(e)

    return False


def generate_gps_data():
    """Generate random GPS data."""
    latitude = random.uniform(-90, 90)
    longitude = random.uniform(-180, 180)
    print "Generated GPS data: Latitude={}, Longitude={}".format(latitude, longitude)
    return {"latitude": latitude, "longitude": longitude}


def generate_vehicle_id():
    """Generate a random vehicle ID."""
    vehicle_id = "vehicle_{}".format(random.randint(1000, 9999))
    print "Generated Vehicle ID: {}".format(vehicle_id)
    return vehicle_id
    
def main():
    """Main vehicle node function."""
    satellites = discover_satellites()

    if not satellites:
        print "No satellites discovered. Exiting..."
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", ACK_LISTEN_PORT))
    print "Listening for ACKs on port {}.".format(ACK_LISTEN_PORT)

    try:
        while True:
            vehicle_id = generate_vehicle_id()
            gps_data = generate_gps_data()

            print "Generated new data - Vehicle ID: {}, GPS: {}".format(vehicle_id, gps_data)

            message = create_message("data", vehicle_id, "satellite", {"gps": gps_data})

            for satellite, details in satellites.items():
                print "Attempting to send data to Satellite {} at {}:{}".format(satellite, details['ip'], details['port'])
                success = send_data(sock, details["ip"], details["port"], message)

                if success:
                    print "Data successfully transmitted and acknowledged by Satellite {}.".format(satellite)
                    break
                else:
                    print "Failed to send data to Satellite {} after {} retries.".format(satellite, MAX_RETRIES)

            print "Waiting for {} seconds before sending the next data packet...".format(DATA_SEND_INTERVAL)
            time.sleep(DATA_SEND_INTERVAL)
    finally:
        sock.close()


if __name__ == "__main__":
    random.seed()
    main()