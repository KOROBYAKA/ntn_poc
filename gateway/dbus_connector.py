import queue
import threading
from dataclasses import dataclass

from gi.repository import GLib
from pydbus import connect

@dataclass
class WirepasPacket:
    gw_rx_timestamp_ms: int
    src: int
    dst: int
    src_ep: int
    dst_ep: int
    travel_time_ms: int
    qos: int
    hop_count: int
    data: bytes

class DbusConnector(threading.Thread):

    def __init__(
        self,
        bus_socket: str,
        service_name: str,
        msg_queue: queue.Queue,
        commander_lock: threading.Lock,
    ):
        super().__init__(name="dbus-connector", daemon=True)

        self.bus_socket = bus_socket
        self.service_name = service_name

        self.msg_queue = msg_queue
        self.commander_lock = commander_lock

        self._loop = None
        self._subscription = None

    def run(self):
        bus_address = f"unix:path={self.bus_socket}"

        bus = connect(bus_address)

        sink = bus.get(
            self.service_name,
            "/com/wirepas/sink",
        )

        data_interface = sink["com.wirepas.sink.data1"]

        self._subscription = data_interface.MessageReceived.connect(
            self._on_message_received
        )

        print(
            f"[DBUS] Connected to {self.service_name} "
            f"via {self.bus_socket}"
        )

        self._loop = GLib.MainLoop()
        self._loop.run()

    def _on_message_received(
        self,
        timestamp_ms,
        src,
        dst,
        src_ep,
        dst_ep,
        travel_time,
        qos,
        hop_count,
        data,
    ):
        # Non-blocking attempt:
        # if AT commander is busy -> packet is discarded.
        if not self.commander_lock.acquire(blocking=False):
            print(
                f"[DBUS] DROP src={src} "
                f"travel={travel_time} ms: commander busy"
            )
            return

        packet = WirepasPacket(
            gw_rx_timestamp_ms=int(timestamp_ms),
            src=int(src),
            dst=int(dst),
            src_ep=int(src_ep),
            dst_ep=int(dst_ep),
            travel_time_ms=int(travel_time),
            qos=int(qos),
            hop_count=int(hop_count),
            data=bytes(data),
        )

        try:
            self.msg_queue.put_nowait(packet)

        except queue.Full:
            # Should normally never happen because commander_lock
            # prevents more than one outstanding packet.
            self.commander_lock.release()

            print("[DBUS] DROP: queue unexpectedly full")
            return

        print(
            print(
                f"[DBUS] ACCEPT "
                f"src={packet.src} "
                f"gw_rx_timestamp={packet.gw_rx_timestamp} "
                f"travel_time={packet.travel_time} ms "
                f"len={len(packet.data)}"
            )
        )

    def stop(self):
        if self._loop is not None:
            self._loop.quit()