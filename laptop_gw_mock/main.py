from functions import *
import serial

def send_once_ntn(
    device_path: str,
    baudrate: int,
    apn: str,
    target_ip: str,
    target_port: int,
    payload: str,
    serial_timeout: float = 0.25,
) -> None:

    with serial.Serial(
        device_path,
        baudrate,
        timeout=serial_timeout,
    ) as ser:

        location = acquire_gnss_fix(ser)

        configure_ntn(
            ser=ser,
            location=location,
            apn=apn,
        )

        start_ntn(ser)

        socket_handle = create_udp_socket(ser)

        try:
            send_udp_payload(
                ser=ser,
                socket_handle=socket_handle,
                target_ip=target_ip,
                target_port=target_port,
                payload=payload,
            )

        finally:
            close_ntn(
                ser=ser,
                socket_handle=socket_handle,
            )

def main():
    send_once_ntn(
        device_path="/dev/ttyACM2",
        baudrate=115200,
        apn="internet.m2mportal.de",
        target_ip="89.106.38.30",
        target_port=9000,
        payload="{'timestamp': '2026-09-03T14:00:00.000000+00:00', 'rssi': -157, 'data': ['53', '45', '4e', '53', '00', '00', '04', '15']}",
        serial_timeout=0.5,
    )

