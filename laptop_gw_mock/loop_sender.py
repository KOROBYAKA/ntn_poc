from functions import *

def at_commander(
    commander_target_device_path: str,
    target_ip: str,
    target_port: int,
    rx_queue: queue.Queue,
    baudrate: int,
    apn: str = "skylo.ip",
    timeout: float = 0.25,
):
    with serial.Serial(
        commander_target_device_path,
        baudrate,
        timeout=timeout,
    ) as ser:

        # 1. Get location once on startup
        location = acquire_gnss_fix(ser)

        # 2. Configure NTN
        configure_ntn(
            ser=ser,
            location=location,
            apn=apn,
        )

        # 3. Connect and wait until actually registered
        start_ntn(ser)

        # 4. Create UDP socket once
        socket_handle = create_udp_socket(ser)

        try:
            while True:
                # Blocking wait for packet from previous pipeline stage
                msg = rx_queue.get()

                try:
                    send_udp_payload(
                        ser=ser,
                        socket_handle=socket_handle,
                        target_ip=target_ip,
                        target_port=target_port,
                        payload=msg,
                    )

                finally:
                    rx_queue.task_done()

        finally:
            close_ntn(
                ser=ser,
                socket_handle=socket_handle,
            )