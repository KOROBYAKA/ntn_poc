import json
import re
import serial
import socket
import time


SERIAL_TARGET = "/dev/pts/2"

def send_serial_line(ser: serial.Serial, line: str):
    print(f"MODEM >> {line}")
    ser.write((line + "\r\n").encode())
    ser.flush()


def parse_xsendto(cmd: str):
    pattern = (
        r'^AT#XSENDTO='
        r'(\d+),'          # socket handle
        r'(\d+),'          # reserved / protocol arg
        r'(\d+),'          # flags
        r'"([^"]+)",'      # IP
        r'(\d+),'          # port
        r'"(.*)"$'         # payload
    )

    match = re.match(pattern, cmd.strip())

    if not match:
        return None

    socket_handle = int(match.group(1))
    flags = int(match.group(3))
    ip = match.group(4)
    dst_port = int(match.group(5))

    raw_payload = match.group(6)

    # at_commander escapes JSON quotes before putting the
    # payload inside the quoted AT argument.
    payload_str = (
        raw_payload
        .replace(r'\"', '"')
        .replace(r'\\', '\\')
    )

    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        payload = payload_str

    return {
        "socket_handle": socket_handle,
        "flags": flags,
        "ip": ip,
        "dst_port": dst_port,
        "data": payload,
    }


def handle_at_command(
    ser: serial.Serial,
    sock: socket.socket,
    cmd: str,
):
    print(f"MODEM << {cmd}")

    # -----------------------------------------------------
    # GNSS setup
    # -----------------------------------------------------

    if cmd == "AT+CFUN=4":
        send_serial_line(ser, "OK")
        return

    if cmd == "AT%XSYSTEMMODE=0,0,1,0,0":
        send_serial_line(ser, "OK")
        return

    if cmd == "AT+CFUN=31":
        send_serial_line(ser, "OK")
        return

    if cmd == "AT#XGNSS=1,0,0,0":
        # send_at() waits for OK first.
        send_serial_line(ser, "OK")

        # acquire_gnss_fix() will then continue reading serial
        # and receives this asynchronous GNSS event.
        time.sleep(0.1)

        send_serial_line(
            ser,
            "#XGNSS: 61.4978,23.7610,120.0,10,0,0,0"
        )
        return

    if cmd == "AT#XGNSS=0":
        send_serial_line(ser, "OK")
        return

    if cmd == "AT+CFUN=30":
        send_serial_line(ser, "OK")
        return

    # -----------------------------------------------------
    # NTN configuration
    # -----------------------------------------------------

    if cmd.startswith("AT%XSYSTEMMODE="):
        send_serial_line(ser, "OK")
        return

    if cmd.startswith("AT%XBANDLOCK="):
        send_serial_line(ser, "OK")
        return

    if cmd.startswith("AT%CELLULARPRFL="):
        send_serial_line(ser, "OK")
        return

    if cmd.startswith("AT+CGDCONT="):
        send_serial_line(ser, "OK")
        return

    if cmd.startswith("AT%LOCATION="):
        send_serial_line(ser, "OK")
        return

    if cmd.startswith("AT+CEREG="):
        send_serial_line(ser, "OK")
        return

    if cmd.startswith("AT+CNEC="):
        send_serial_line(ser, "OK")
        return

    if cmd.startswith("AT+CSCON="):
        send_serial_line(ser, "OK")
        return

    if cmd.startswith("AT%MDMEV="):
        send_serial_line(ser, "OK")
        return

    # -----------------------------------------------------
    # Start NTN + registration
    # -----------------------------------------------------

    if cmd == "AT+CFUN=1":
        # send_at() collects everything before OK into its
        # response_lines, therefore CEREG can arrive here.
        send_serial_line(ser, "+CEREG: 1")
        send_serial_line(ser, "OK")
        return

    # -----------------------------------------------------
    # Socket
    # -----------------------------------------------------

    if cmd == "AT#XSOCKET=1,2,0":
        # create_udp_socket() searches this line for handle.
        send_serial_line(ser, "#XSOCKET: 0")
        send_serial_line(ser, "OK")
        return

    if cmd.startswith("AT#XCLOSE="):
        send_serial_line(ser, "OK")
        return

    # -----------------------------------------------------
    # UDP transmission
    # -----------------------------------------------------

    if cmd.startswith("AT#XSENDTO="):
        send_data = parse_xsendto(cmd)

        if send_data is None:
            send_serial_line(ser, "ERROR")
            return

        print(
            "AT_modem_mock::send_data:",
            send_data,
        )

        # Send real UDP packet to backend.
        #
        # Keep JSON as JSON instead of Python str(dict).
        if isinstance(send_data["data"], (dict, list)):
            udp_payload = json.dumps(
                send_data["data"],
                separators=(",", ":"),
            )
        else:
            udp_payload = str(send_data["data"])

        sock.sendto(
            udp_payload.encode(),
            (
                send_data["ip"],
                send_data["dst_port"],
            ),
        )

        # AT command itself succeeded.
        send_serial_line(ser, "OK")

        # Simulate asynchronous NTN transmission delay.
        time.sleep(0.5)

        # at_commander waits for this after OK.
        send_serial_line(
            ser,
            "#XSENDNTF: 0,0"
        )

        return

    # -----------------------------------------------------
    # Unknown command
    # -----------------------------------------------------

    print(f"Unknown AT command: {cmd}")
    send_serial_line(ser, "ERROR")


def main():
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    with serial.Serial(
        SERIAL_TARGET,
        115200,
        timeout=1,
    ) as ser:

        print(
            f"AT modem mock listening on "
            f"{SERIAL_TARGET}"
        )

        while True:
            raw = ser.readline()

            if not raw:
                continue

            cmd = raw.decode(
                errors="replace"
            ).strip()

            if not cmd:
                continue

            handle_at_command(
                ser=ser,
                sock=sock,
                cmd=cmd,
            )


if __name__ == "__main__":
    main()