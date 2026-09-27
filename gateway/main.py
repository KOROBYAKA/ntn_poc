import os
import threading
import queue
import time

from at_commander import at_commander
from dbus_connector import DbusConnector






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