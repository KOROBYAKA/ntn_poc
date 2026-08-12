import serial
import queue

def uart_worker(device_path, baudrate: int, tx_queue: queue.Queue, timeout: float = 0.25):
    print(f"uart_worker::opening::{device_path}", flush=True)
    with serial.Serial(device_path, baudrate, timeout=timeout) as ser:
        print(f"uart_worker::opened::{device_path}", flush=True)
        while True:

            line = ser.readline().decode()  # read a '\n' terminated line
            if line != '':
                print(f"uart_worker::line::{line}", flush=True)
                packet_to_send = packet_handler(line)
                tx_queue.put(packet_to_send)
                print("uart_worker::msg_put()", flush=True)


def packet_handler(packet: str):

    return packet




