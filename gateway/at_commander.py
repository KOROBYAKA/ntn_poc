import csv
import re
import time
import serial
import queue
import threading
import json
from datetime import datetime, timezone


def timestamp_ms_to_local(timestamp_ms: int) -> str:
    return (
        datetime
        .fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        .astimezone()
        .isoformat(timespec="milliseconds")
    )

def at_commander(
    commander_target_device_path: str,
    target_ip: str,
    target_port: int,
    rx_queue: queue.Queue,
    commander_lock: threading.Lock,
    baudrate: int,
    apn: str = "skylo.ip",
    timeout: float = 0.25,
):
    """
    NTN worker.

    Lock semantics:
        LOCKED   -> AT Commander is busy / not ready
        UNLOCKED -> AT Commander can accept one new packet

    The D-Bus connector acquires commander_lock before placing
    a packet into rx_queue.

    AT Commander releases commander_lock only after the complete
    NTN send operation has finished.
    """

    with serial.Serial(
        commander_target_device_path,
        baudrate,
        timeout=timeout,
    ) as ser:

        socket_handle = None

        try:
            print("[AT] Starting NTN initialization")

            # Acquire location once on startup.
            location = acquire_gnss_fix(ser)

            # Configure modem for NTN.
            configure_ntn(
                ser=ser,
                location=location,
                apn=apn,
            )

            # Start modem and wait until network registration.
            start_ntn(ser)

            # Create UDP socket once and reuse it.
            socket_handle = create_udp_socket(ser)

            print("[AT] NTN initialization complete")

            # main.py starts with this lock acquired.
            # Releasing it means that D-Bus may now accept
            # the first packet.
            if commander_lock.locked():
                commander_lock.release()

            print("[AT] Commander READY")

            while True:
                # Blocks without consuming CPU until D-Bus connector
                # places one accepted packet into the queue.
                msg = rx_queue.get()

                try:
                    print("[AT] Packet received from D-Bus")
                    print("[AT] Starting NTN transmission")

                    # If dbus_connector passes a WirepasPacket object,
                    # extract its payload.
                    if hasattr(msg, "data"):
                        backend_payload = {
                            "src": msg.src,
                            "gw_rx_timestamp":
                                msg.gw_rx_timestamp,
                            "travel_time": msg.travel_time,
                            "data": msg.data.hex(),
                        }
                        
                        payload = json.dumps(
                            backend_payload,
                            separators=(",", ":"),
                        )

                        print(payload)

                    else:
                        payload = msg

                    send_udp_payload(
                        ser=ser,
                        socket_handle=socket_handle,
                        target_ip=target_ip,
                        target_port=target_port,
                        payload=payload,
                    )

                    print("[AT] NTN transmission completed")

                    # The send operation, including #XSENDNTF,
                    # has completed. Allow D-Bus connector to accept
                    # one new packet.
                    commander_lock.release()

                    print("[AT] Commander READY")

                except Exception as exc:
                    # Fail closed:
                    # do NOT release the lock here.
                    #
                    # We don't know whether the modem/socket is still
                    # in a valid state after an NTN transmission error.
                    print(f"[AT] Transmission failed: {exc}")
                    raise

                finally:
                    rx_queue.task_done()

        finally:
            if socket_handle is not None:
                try:
                    close_ntn(
                        ser=ser,
                        socket_handle=socket_handle,
                    )
                except Exception as exc:
                    print(f"[AT] NTN shutdown failed: {exc}")


def create_ip_packet(
    msg: str | bytes,
    target_ip: str,
    target_port: int,
    socket_handle: int = 0,
    wait_ack: bool = True,
) -> str:
    """
    Create AT command for sending UDP/IP payload over
    an already configured NTN PDN.

    This does not create a real IP packet. The modem creates
    the UDP/IP packet internally.
    """

    # Request asynchronous NTN send notification.
    flags = 8192 if wait_ack else 0

    if isinstance(msg, bytes):
        # Do not silently turn bytes into "b'...'"
        # because that would change the actual application payload.
        try:
            payload = msg.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                "Wirepas payload is binary and cannot be sent "
                "as the current text-based AT payload. "
                "Define an explicit binary encoding first."
            ) from exc
    else:
        payload = str(msg)

    payload = payload.strip()

    # Escape characters significant inside the quoted AT argument.
    payload = payload.replace("\\", "\\\\").replace('"', '\\"')

    return (
        f'AT#XSENDTO={socket_handle},0,{flags},'
        f'"{target_ip}",{target_port},"{payload}"'
    )


def read_line(ser: serial.Serial) -> str:
    raw = ser.readline()

    if not raw:
        return ""

    line = raw.decode(
        "utf-8",
        errors="replace",
    ).strip()

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

        # Some modem/terminal configurations echo the command.
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

        # Information responses and asynchronous URCs can appear
        # before the final OK.
        response_lines.append(line)

    raise TimeoutError(
        f"Timeout waiting for response to: {command}"
    )


def parse_gnss_fix(line: str) -> dict | None:
    if not line.startswith("#XGNSS:"):
        return None

    payload = line.removeprefix("#XGNSS:").strip()

    fields = next(
        csv.reader(
            [payload],
            skipinitialspace=True,
        )
    )

    # "#XGNSS: 1,1" etc. are events rather than fixes.
    if len(fields) < 7:
        return None

    try:
        latitude = fields[0]
        longitude = fields[1]
        altitude = fields[2]
        accuracy = int(float(fields[3]))

        # Validate coordinates.
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

    initial_lines = send_at(
        ser,
        "AT#XGNSS=1,0,0,0",
    )

    deadline = time.monotonic() + timeout_s

    try:
        # The fix may theoretically arrive before final OK.
        for line in initial_lines:
            fix = parse_gnss_fix(line)

            if fix:
                print(f"[AT] GNSS fix acquired: {fix}")
                return fix

        while time.monotonic() < deadline:
            line = read_line(ser)

            if not line:
                continue

            fix = parse_gnss_fix(line)

            if fix:
                print(f"[AT] GNSS fix acquired: {fix}")
                return fix

        raise TimeoutError("GNSS fix timeout")

    finally:
        send_at(ser, "AT#XGNSS=0")
        send_at(ser, "AT+CFUN=30")


def configure_ntn(
    ser: serial.Serial,
    location: dict,
    apn: str,
    bands: str = "23,255,256",
) -> None:

    # Switch from GNSS system mode to NTN NB-IoT.
    send_at(
        ser,
        "AT%XSYSTEMMODE=0,0,0,0,1",
    )

    # Runtime band lock.
    send_at(
        ser,
        f'AT%XBANDLOCK=2,,"{bands}"',
    )

    # NTN cellular profile.
    send_at(
        ser,
        "AT%CELLULARPRFL=2,0,4,0",
    )

    # Default PDN.
    send_at(
        ser,
        f'AT+CGDCONT=0,"ip","{apn}"',
    )

    # Supply GNSS position to NTN stack.
    send_at(
        ser,
        'AT%LOCATION=2,'
        f'"{location["latitude"]}",'
        f'"{location["longitude"]}",'
        f'"{location["altitude"]}",'
        f'{location["accuracy"]},0'
    )

    # Enable useful modem notifications.
    send_at(ser, "AT%CELLULARPRFL=1")
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
            print("[AT] NTN registered")
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
                "NTN registration failed: "
                "no suitable NTN cell"
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

    raise TimeoutError(
        "Timeout waiting for NTN registration"
    )


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
        ser=ser,
        initial_lines=lines,
        timeout_s=timeout_s,
    )


def create_udp_socket(
    ser: serial.Serial,
) -> int:

    lines = send_at(
        ser,
        "AT#XSOCKET=1,2,0",
    )

    for line in lines:
        match = re.search(
            r"#XSOCKET:\s*(\d+)",
            line,
        )

        if match:
            handle = int(match.group(1))

            print(
                f"[AT] UDP socket created: "
                f"handle={handle}"
            )

            return handle

    raise RuntimeError(
        "Socket was created but handle "
        f"wasn't found: {lines}"
    )


def wait_for_send_ack(
    ser: serial.Serial,
    initial_lines: list[str],
    timeout_s: float = 120.0,
) -> None:

    for line in initial_lines:
        if line.startswith("#XSENDNTF"):
            print(
                f"[AT] Payload acknowledged: {line}"
            )
            return

    deadline = time.monotonic() + timeout_s

    while time.monotonic() < deadline:
        line = read_line(ser)

        if not line:
            continue

        if line.startswith("#XSENDNTF"):
            print(
                f"[AT] Payload acknowledged: {line}"
            )
            return

    raise TimeoutError(
        "Timeout waiting for #XSENDNTF"
    )


def send_udp_payload(
    ser: serial.Serial,
    socket_handle: int,
    target_ip: str,
    target_port: int,
    payload: str | bytes,
) -> None:

    command = create_ip_packet(
        msg=payload,
        target_ip=target_ip,
        target_port=target_port,
        socket_handle=socket_handle,
        wait_ack=True,
    )

    send_start = time.monotonic()

    lines = send_at(
        ser,
        command,
        timeout_s=10.0,
    )

    wait_for_send_ack(
        ser=ser,
        initial_lines=lines,
    )

    send_duration = time.monotonic() - send_start

    print(
        f"[AT] NTN send duration: "
        f"{send_duration:.3f} s"
    )


def close_ntn(
    ser: serial.Serial,
    socket_handle: int,
) -> None:

    send_at(
        ser,
        f"AT#XCLOSE={socket_handle}",
    )

    send_at(
        ser,
        "AT+CFUN=4",
    )