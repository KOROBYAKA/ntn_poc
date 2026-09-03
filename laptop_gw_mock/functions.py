import csv
import re
import time
import serial


def create_ip_packet(
    msg: str,
    target_ip: str,
    target_port: int,
    socket_handle: int = 0,
    wait_ack: bool = True,
) -> str:
    """
    Create AT command for sending UDP/IP payload over already configured NTN PDN.

    This does not create a real IP packet.
    It creates Serial Modem AT command:
    AT#XSENDTO=<handle>,<mode>,<flags>,"<ip>",<port>,"<payload>"
    """

    # NTN radio-level async acknowledgment flag.
    # 8192 means modem should emit #XSENDNTF when uplink is acknowledged.
    flags = 8192 if wait_ack else 0

    # Keep payload one-line and avoid breaking AT command string.
    payload = str(msg).strip()

    # Minimal escaping for AT string arguments.
    payload = payload.replace("\\", "\\\\").replace('"', '\\"')

    return (
        f'AT#XSENDTO={socket_handle},0,{flags},'
        f'"{target_ip}",{target_port},"{payload}"'
    )


def read_line(ser: serial.Serial) -> str:
    raw = ser.readline()

    if not raw:
        return ""

    line = raw.decode("utf-8", errors="replace").strip()

    if line:
        print(f"<< {line}")

    return line


def send_at(
    ser: serial.Serial,
    command: str,
    timeout_s: float = 5.0,
) -> list[str]:
    print(f">> {command}")

    ser.write((command + "\r\n").encode("ascii"))
    ser.flush()

    deadline = time.monotonic() + timeout_s
    response_lines = []

    while time.monotonic() < deadline:
        line = read_line(ser)

        if not line:
            continue

        # Some terminal configurations echo the sent command.
        if line == command:
            continue

        if line == "OK":
            return response_lines

        if (
            line == "ERROR"
            or line.startswith("+CME ERROR")
            or line.startswith("+CMS ERROR")
        ):
            raise RuntimeError(
                f"AT command failed: {command}: {line}"
            )

        # Information responses and URCs may appear before OK.
        response_lines.append(line)

    raise TimeoutError(f"Timeout waiting for response to: {command}")

def parse_gnss_fix(line: str) -> dict | None:
    if not line.startswith("#XGNSS:"):
        return None

    payload = line.removeprefix("#XGNSS:").strip()
    fields = next(csv.reader([payload], skipinitialspace=True))

    # "#XGNSS: 1,1" and "#XGNSS: 1,4"
    # are events, not position fixes.
    if len(fields) < 7:
        return None

    try:
        latitude = fields[0]
        longitude = fields[1]
        altitude = fields[2]
        accuracy = int(float(fields[3]))

        # Validation that first fields really are coordinates.
        float(latitude)
        float(longitude)
        float(altitude)

    except (ValueError, IndexError):
        return None

    return {
        "latitude": latitude,
        "longitude": longitude,
        "altitude": altitude,
        "accuracy": accuracy,
    }


def acquire_gnss_fix(
    ser: serial.Serial,
    timeout_s: float = 180.0,
) -> dict:

    send_at(ser, "AT+CFUN=4")
    send_at(ser, "AT%XSYSTEMMODE=0,0,1,0,0")
    send_at(ser, "AT+CFUN=31")
    initial_lines = send_at(ser, "AT#XGNSS=1,0,0,0")

    deadline = time.monotonic() + timeout_s

    try:
        # In case fix appeared before command OK.
        for line in initial_lines:
            fix = parse_gnss_fix(line)
            if fix:
                print(f"GNSS fix acquired: {fix}")
                return fix

        while time.monotonic() < deadline:
            line = read_line(ser)

            if not line:
                continue

            fix = parse_gnss_fix(line)

            if fix:
                print(f"GNSS fix acquired: {fix}")
                return fix

        raise TimeoutError("GNSS fix timeout")

    finally:
        # Shut down GNSS as required by the guide.
        send_at(ser, "AT#XGNSS=0")
        send_at(ser, "AT+CFUN=30")

def configure_ntn(
    ser: serial.Serial,
    location: dict,
    apn: str,
    bands: str = "23,255,256",
) -> None:

    # Switch modem from GNSS system mode to NTN NB-IoT.
    send_at(ser, "AT%XSYSTEMMODE=0,0,0,0,1")

    # Recommended runtime band lock.
    send_at(ser, f'AT%XBANDLOCK=2,,"{bands}"')

    # NTN cellular profile:
    # CPID=0, AcT=4 (NTN NB-IoT), physical SIM/eSIM.
    send_at(ser, "AT%CELLULARPRFL=2,0,4,0")

    # Default PDN connection for profile 0 / CID 0.
    send_at(ser, f'AT+CGDCONT=0,"ip","{apn}"')

    # Give freshly acquired GNSS position to NTN stack.
    send_at(
        ser,
        'AT%LOCATION=2,'
        f'"{location["latitude"]}",'
        f'"{location["longitude"]}",'
        f'"{location["altitude"]}",'
        f'{location["accuracy"]},0'
    )

    # Cellular profile change notifications.
    send_at(ser, "AT%CELLULARPRFL=1")

    # Diagnostic/event notifications.
    send_at(ser, "AT+CEREG=5")
    send_at(ser, "AT+CNEC=24")
    send_at(ser, "AT+CSCON=3")
    send_at(ser, "AT%MDMEV=2")

def parse_cereg_urc(line: str) -> int | None:
    if not line.startswith("+CEREG:"):
        return None

    payload = line.removeprefix("+CEREG:").strip()

    try:
        first_field = payload.split(",", 1)[0]
        return int(first_field)
    except ValueError:
        return None


def wait_for_ntn_registration(
    ser: serial.Serial,
    initial_lines: list[str],
    timeout_s: float = 180.0,
) -> None:

    def process(line: str) -> bool:
        stat = parse_cereg_urc(line)

        if stat is None:
            return False

        if stat in (1, 5):
            print("NTN registered")
            return True

        if stat == 3:
            raise RuntimeError(
                f"NTN registration rejected: {line}"
            )

        if stat == 90:
            raise RuntimeError(
                "NTN registration failed: UICC failure"
            )

        if stat == 91:
            raise RuntimeError(
                "NTN registration failed: no suitable NTN cell"
            )

        return False

    for line in initial_lines:
        if process(line):
            return

    deadline = time.monotonic() + timeout_s

    while time.monotonic() < deadline:
        line = read_line(ser)

        if not line:
            continue

        if process(line):
            return

    raise TimeoutError("Timeout waiting for NTN registration")


def start_ntn(
    ser: serial.Serial,
    timeout_s: float = 180.0,
) -> None:

    lines = send_at(
        ser,
        "AT+CFUN=1",
        timeout_s=10.0,
    )

    wait_for_ntn_registration(
        ser,
        initial_lines=lines,
        timeout_s=timeout_s,
    )

def create_udp_socket(ser: serial.Serial) -> int:
    lines = send_at(ser, "AT#XSOCKET=1,2,0")

    for line in lines:
        match = re.search(r"#XSOCKET:\s*(\d+)", line)

        if match:
            handle = int(match.group(1))
            print(f"UDP socket created: handle={handle}")
            return handle

    raise RuntimeError(
        f"Socket was created but handle wasn't found: {lines}"
    )


def wait_for_send_ack(
    ser: serial.Serial,
    initial_lines: list[str],
    timeout_s: float = 120.0,
) -> None:

    for line in initial_lines:
        if line.startswith("#XSENDNTF"):
            print(f"Payload acknowledged: {line}")
            return

    deadline = time.monotonic() + timeout_s

    while time.monotonic() < deadline:
        line = read_line(ser)

        if not line:
            continue

        if line.startswith("#XSENDNTF"):
            print(f"Payload acknowledged: {line}")
            return

    raise TimeoutError("Timeout waiting for #XSENDNTF")

def send_udp_payload(
    ser: serial.Serial,
    socket_handle: int,
    target_ip: str,
    target_port: int,
    payload: str,
) -> None:

    command = create_ip_packet(
        msg=payload,
        target_ip=target_ip,
        target_port=target_port,
        socket_handle=socket_handle,
        wait_ack=True,
    )

    lines = send_at(
        ser,
        command,
        timeout_s=10.0,
    )

    wait_for_send_ack(
        ser,
        initial_lines=lines,
    )

def close_ntn(
    ser: serial.Serial,
    socket_handle: int,
) -> None:

    send_at(ser, f"AT#XCLOSE={socket_handle}")
    send_at(ser, "AT+CFUN=4")
