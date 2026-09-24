import os
import threading
import queue
import time
import ntplib

from at_commander import at_commander
from dbus_connector import DbusConnector

def measure_ntp_offset(
    ntp_server: str,
    samples_count: int = 20,
    timeout: float = 2.0,
) -> dict:

    client = ntplib.NTPClient()
    samples = []

    for i in range(samples_count):
        response = client.request(
            ntp_server,
            version=4,
            timeout=timeout,
        )

        sample = {
            "sample": i,
            "delay": response.delay,
            "offset": response.offset,
            "stratum": response.stratum,
            "tx_time": response.tx_time,
            "dest_time": response.dest_time,
        }

        samples.append(sample)

        print(
            f"[NTP] sample={i:02d} "
            f"delay={sample['delay'] * 1000:.3f} ms "
            f"offset={sample['offset'] * 1000:.3f} ms"
        )

    best_sample = min(
        samples,
        key=lambda sample: sample["delay"],
    )

    print(
        f"[NTP] Best sample: "
        f"delay={best_sample['delay'] * 1000:.3f} ms, "
        f"offset={best_sample['offset'] * 1000:.3f} ms"
    )

    return best_sample

def apply_clock_offset(offset: float) -> None:
    current_time = time.clock_gettime(
        time.CLOCK_REALTIME
    )

    corrected_time = current_time + offset

    print(
        f"[NTP] Applying clock offset: "
        f"{offset * 1000:.3f} ms"
    )

    time.clock_settime(
        time.CLOCK_REALTIME,
        corrected_time,
    )







def main():




    commander_target_device_path = os.getenv(
        "NTN_DEVICE",
        "/dev/ntn_modem",
    )

    target_ip = os.getenv(
        "NTN_TARGET_IP",
        "127.0.0.1",
    )

    target_port = int(
        os.getenv("NTN_TARGET_PORT", "9000")
    )

    baudrate_at = int(
        os.getenv("NTN_BAUDRATE", "115200")
    )

    apn = os.getenv(
        "NTN_APN",
        "skylo.ip",
    )

    bus_socket = os.getenv(
        "DBUS_SOCKET",
        "/var/run/dbus/system_bus_socket",
    )

    service_name = os.getenv(
        "DBUS_SERVICE",
        "com.wirepas.sink.sink1",
    )

    best_sample = measure_ntp_offset(
        ntp_server=ntp_server,
    )

    apply_clock_offset(
        best_sample["offset"]
    )

    print("NTP Synchronization is done\n\n###################################\n\n\n")

    msg_queue = queue.Queue(maxsize=1)

    commander_lock = threading.Lock()
    commander_lock.acquire()

    commander_thread = threading.Thread(
        target=at_commander,
        name="at-commander",
        args=(
            commander_target_device_path,
            target_ip,
            target_port,
            msg_queue,
            commander_lock,
            baudrate_at,
            apn,
        ),
    )

    dbus_thread = DbusConnector(
        bus_socket=bus_socket,
        service_name=service_name,
        msg_queue=msg_queue,
        commander_lock=commander_lock,
    )

    commander_thread.start()
    dbus_thread.start()

    commander_thread.join()


if __name__ == "__main__":
    main()