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

def init_ntn_udp_modem(
    ser: serial.Serial,
    apn: str,
    latitude: str,
    longitude: str,
    altitude: str = "0",
    bands: str = "23,255,256",
    do_factory_reset: bool = False,
) -> None:
    # Put modem into offline/minimum functionality mode before changing radio settings.
    send_at(ser, "AT+CFUN=0")

    # Optional: reset modem settings.
    # Use only during clean test setup, not before every normal transmission.
    if do_factory_reset:
        send_at(ser, "AT%XFACTORYRESET=0", delay_s=1.0)

    # Set modem system mode to NB-IoT NTN.
    # Parameters mean: LTE-M=0, NB-IoT=0, GNSS=0, LTE preference=0, NTN=1.
    send_at(ser, "AT%XSYSTEMMODE=0,0,0,0,1")

    # Restrict modem search to NTN bands.
    # B23/B255/B256 are NTN bands; for Europe/Skylo-like testing B256 is usually important.
    send_at(ser, f'AT%XBANDLOCK=2,,"{bands}"')

    # Provide device location to the NTN stack.
    # For static PoC this can be set manually; for mobile device update it when position changes.
    send_at(
        ser,
        f'AT%LOCATION=2,"{latitude}","{longitude}","{altitude}",10,0'
    )

    # Configure initial PDN context for IPv4/UDP data.
    # APN must come from the SIM/connectivity provider: DT, Monogoto, Skylo profile, etc.
    send_at(ser, f'AT+CGDCONT=0,"ip","{apn}"')

    # Subscribe to modem domain events.
    # Useful for seeing attach, detach, modem state changes and other modem-level events.
    send_at(ser, "AT%MDMEV=2")

    # Subscribe to RRC connection state indications.
    # Useful to see when modem enters/leaves connected state.
    send_at(ser, "AT+CSCON=3")

    # Subscribe to network registration status indications.
    # CEREG=5 gives detailed unsolicited registration updates.
    send_at(ser, "AT+CEREG=5")

    # Subscribe to network error code reporting.
    # Useful for attach reject / network-side problems.
    send_at(ser, "AT+CNEC=24")

    # Enable full modem functionality and start network search/attach.
    send_at(ser, "AT+CFUN=1", delay_s=1.0)

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

