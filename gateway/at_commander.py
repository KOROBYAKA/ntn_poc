import time
import queue
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


def send_at(ser: serial.Serial, command: str, delay_s: float = 0.2) -> None:
    '''
    Minimal AT sender.
    Later this should be extended to wait for OK/ERROR and parse URC events.
    '''
    ser.write((command + "\r\n").encode("ascii"))
    ser.flush()
    time.sleep(delay_s)

def read_modem_line(ser: serial.Serial) -> str | None:
    """
    Read one modem line.
    Returns None on serial timeout.
    """
    raw = ser.readline()

    if not raw:
        return None

    return raw.decode("ascii", errors="replace").strip()


def parse_gnss_fix(line: str) -> dict | None:
    """
    Parse GNSS fix line.

    Expected useful line:
    #XGNSS: 60.400130,20.178765,182.815308,66.373810,0.444368,0.000000,"2025-07-09 20:08:01"

    Ignore state lines like:
    #XGNSS: 1,1
    #XGNSS: 1,4
    """
    if not line.startswith("#XGNSS:"):
        return None

    body = line.removeprefix("#XGNSS:").strip()
    parts = [part.strip().strip('"') for part in body.split(",")]

    # State lines have only two fields, real fix line has latitude/longitude/altitude/etc.
    if len(parts) < 6:
        return None

    try:
        latitude = parts[0]
        longitude = parts[1]
        altitude = parts[2]

        # Nordic example later passes this value as accuracy in AT%LOCATION.
        accuracy = int(round(float(parts[3])))

        # Validate that first fields are numeric.
        float(latitude)
        float(longitude)
        float(altitude)

    except ValueError:
        return None

    return {
        "latitude": latitude,
        "longitude": longitude,
        "altitude": altitude,
        "accuracy": accuracy,
        "raw": line,
    }


def acquire_gnss_location(
    ser: serial.Serial,
    fix_timeout_s: float = 180.0,
    preserve_ntn_context: bool = False,
) -> dict:
    """
    Acquire GNSS location using nRF9151 internal GNSS.

    If preserve_ntn_context=False:
        use initial GNSS acquisition flow.

    If preserve_ntn_context=True:
        use CFUN=45 first, preserving existing NTN PDN context.
    """

    # If NTN connection already exists, CFUN=45 puts NTN on hold and preserves PDN context.
    # For initial startup, CFUN=4 is enough to put modem offline before GNSS mode.
    if preserve_ntn_context:
        send_at(ser, "AT+CFUN=45", delay_s=1.0)
    else:
        send_at(ser, "AT+CFUN=4", delay_s=1.0)

    # Enable GNSS-only system mode.
    # Parameters mean: LTE-M=0, NB-IoT=0, GNSS=1, LTE preference=0, NTN=0.
    send_at(ser, "AT%XSYSTEMMODE=0,0,1,0,0")

    # Start GNSS functionality mode.
    send_at(ser, "AT+CFUN=31", delay_s=1.0)

    # Start GNSS acquisition.
    send_at(ser, "AT#XGNSS=1,0,0,0")

    deadline = time.monotonic() + fix_timeout_s

    while time.monotonic() < deadline:
        line = read_modem_line(ser)

        if line is None:
            continue

        print(f"GNSS::{line}")

        fix = parse_gnss_fix(line)

        if fix is not None:
            # Stop GNSS stack after successful fix.
            send_at(ser, "AT#XGNSS=0", delay_s=0.5)

            # Turn GNSS off.
            send_at(ser, "AT+CFUN=30", delay_s=1.0)

            return fix

    # Try to cleanly stop GNSS even if fix was not acquired.
    send_at(ser, "AT#XGNSS=0", delay_s=0.5)
    send_at(ser, "AT+CFUN=30", delay_s=1.0)

    raise TimeoutError(f"GNSS fix was not acquired within {fix_timeout_s} seconds")



def init_ntn_udp_modem(
    ser: serial.Serial,
    apn: str,
    latitude: str | None = None,
    longitude: str | None = None,
    altitude: str = "0",
    bands: str = "23,255,256",
    do_factory_reset: bool = False,
    use_internal_gnss: bool = True,
) -> dict | None:
    gnss_fix = None

    # Optional: reset modem settings.
    # Use only during clean test setup, not before every normal transmission.
    if do_factory_reset:
        send_at(ser, "AT+CFUN=0", delay_s=1.0)
        send_at(ser, "AT%XFACTORYRESET=0", delay_s=1.0)

    # Acquire location from internal nRF9151 GNSS.
    # This replaces manually hardcoded latitude/longitude/altitude.
    if use_internal_gnss:
        gnss_fix = acquire_gnss_location(
            ser=ser,
            fix_timeout_s=180.0,
            preserve_ntn_context=False,
        )

        latitude = gnss_fix["latitude"]
        longitude = gnss_fix["longitude"]
        altitude = gnss_fix["altitude"]
        accuracy = gnss_fix["accuracy"]

    else:
        # Manual/external location mode.
        # In this mode latitude and longitude must be provided by caller.
        if latitude is None or longitude is None:
            raise ValueError("latitude and longitude are required when use_internal_gnss=False")

        accuracy = 10

        # Put modem into offline/minimum functionality mode before changing radio settings.
        send_at(ser, "AT+CFUN=0", delay_s=1.0)

    # Set modem system mode to NB-IoT NTN.
    # Parameters mean: LTE-M=0, NB-IoT=0, GNSS=0, LTE preference=0, NTN=1.
    send_at(ser, "AT%XSYSTEMMODE=0,0,0,0,1")

    # Restrict modem search to NTN bands.
    # B23/B255/B256 are NTN bands.
    send_at(ser, f'AT%XBANDLOCK=2,,"{bands}"')

    # Create cellular profiles for NTN and TN.
    # In Nordic GNSS flow, TN profile is used for GNSS-related switching,
    # even if TN data communication is not tested.
    send_at(ser, "AT%CELLULARPRFL=2,0,4,0")  # NTN profile
    send_at(ser, "AT%CELLULARPRFL=2,1,1,0")  # TN profile

    # Configure initial PDN context for IPv4/UDP data on NTN profile.
    send_at(ser, f'AT+CGDCONT=0,"ip","{apn}"')

    # Configure PDN context for TN profile as well, because two cellular profiles are in use.
    send_at(ser, f'AT+CGDCONT=10,"ip","{apn}"')

    # Provide acquired/manual location to NTN stack.
    send_at(
        ser,
        f'AT%LOCATION=2,"{latitude}","{longitude}","{altitude}",{accuracy},0'
    )

    # Subscribe to profile change notifications.
    send_at(ser, "AT%CELLULARPRFL=1")

    # Subscribe to modem domain events.
    send_at(ser, "AT%MDMEV=2")

    # Subscribe to RRC connection state indications.
    send_at(ser, "AT+CSCON=3")

    # Subscribe to network registration status indications.
    send_at(ser, "AT+CEREG=5")

    # Subscribe to network error code reporting.
    send_at(ser, "AT+CNEC=24")

    # Enable full modem functionality and start NTN network search/attach.
    send_at(ser, "AT+CFUN=1", delay_s=1.0)

    return gnss_fix
def at_commander(commander_target_device_path: str, target_ip:str, target_port:int,
                 rx_queue: queue.Queue, baudrate:int, timeout: int = 0.25):

    with serial.Serial(commander_target_device_path, baudrate, timeout=timeout) as ser:
        # Initialization
        # Initialization: configure nRF9151 Serial Modem for NB-IoT NTN UDP/IP.
        init_ntn_udp_modem(
            ser=ser,
            apn="skylo.ip",  # Replace with APN from your SIM provider.
            latitude="61.4978",  # Replace with real gateway latitude.
            longitude="23.7610",  # Replace with real gateway longitude.
            altitude="0",
            bands="23,255,256",
            do_factory_reset=False,
        )
        while True:
            msg = rx_queue.get()

            cmd = create_ip_packet(
                msg=msg,
                target_ip=target_ip,
                target_port=target_port,
                socket_handle=0,
                wait_ack=True,
            )
            send_at(ser, cmd)

