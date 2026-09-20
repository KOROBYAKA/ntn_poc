from at_commander import at_commander
from dbus_connector import DbusConnector

import threading
import queue


def main():
    # AT Commander configuration
    commander_target_device_path = "/dev/pts/4"
    target_ip = "127.0.0.1"
    target_port = 9000
    baudrate_at = 115200

    # Wirepas D-Bus configuration
    bus_socket = "/var/run/dbus/system_bus_socket"
    service_name = "com.wirepas.sink.sink1"

    # Shared IPC between D-Bus connector and AT Commander.
    #
    # Only one packet may ever wait for AT Commander.
    msg_queue = queue.Queue(maxsize=1)

    # Shared state:
    #
    # LOCKED   -> AT Commander busy / not initialized
    # UNLOCKED -> AT Commander ready for one packet
    commander_lock = threading.Lock()

    # Initially AT Commander is NOT ready.
    # It will release this lock after NTN initialization.
    commander_lock.acquire()

    # AT Commander runs as its own worker thread.
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
        ),
    )

    # DbusConnector already inherits from threading.Thread.
    dbus_thread = DbusConnector(
        bus_socket=bus_socket,
        service_name=service_name,
        msg_queue=msg_queue,
        commander_lock=commander_lock,
    )

    commander_thread.start()
    dbus_thread.start()

    # AT Commander is currently the main worker whose lifetime
    # determines the lifetime of the application.
    commander_thread.join()


if __name__ == "__main__":
    main()