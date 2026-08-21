import serial
import socket
import re
import json

SERIAL_TARGET = "/dev/pts/3"

UDP_IP = "127.0.0.1"
UDP_PORT = 5005

def parse_AT_cmd(cmd: str):
    pattern = r'^(AT[#\+]?\w+)=[^,]+,[^,]+,[^,]+,"([^"]+)",(\d+),"(.*)"$'
    match = re.match(pattern, cmd.strip())

    if not match:
        return None

    cmd = match.group(1)
    ip = match.group(2)
    dst_port = int(match.group(3))
    raw_payload_str = match.group(4)

    json_ready_str = raw_payload_str.replace("'", '"')
    parsed_payload = json.loads(json_ready_str)

    return {
        "cmd": cmd,
        "ip": ip,
        "dst_port": dst_port,
        "data": parsed_payload,
    }

def main():
    sock = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)

    with serial.Serial(SERIAL_TARGET, 115200, timeout=1) as ser:

        while True:
            msg = ser.readline().decode()
            send_data = parse_AT_cmd(msg)
            if send_data is None:
                continue
            print(send_data)


if __name__ == "__main__":
    main()