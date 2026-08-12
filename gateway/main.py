import uart_reader
from uart_reader import uart_worker
from at_commander import at_commander
from message_handler import message_handler
import threading
import time
import queue

def main():
    threads = []

# SETUP UART_READER thread
    uart_reader_device_path = "/dev/pts/8"
    uart_handler_queue = queue.Queue(100)
    baudrate = 115200
    #timer is optional for the thread main function
    uart_reader_thread = threading.Thread(target=uart_worker, args=(uart_reader_device_path,
                                                                    baudrate,
                                                                    uart_handler_queue))
    threads.append(uart_reader_thread)

    # SETUP MESSAGE_HANDLER thread
    handler_commander_queue = queue.Queue(100)
    handler_thread = threading.Thread(target=message_handler, args=(uart_handler_queue,
                                                                    handler_commander_queue))
    threads.append(handler_thread)

# SETUP AT_COMMANDER thread
    commander_target_device_path = "/dev/pts/5"
    target_ip = "127.0.0.1"
    target_port = 9000
    baudrate_AT = 115200
    commander_thread = threading.Thread(target=at_commander, args=(commander_target_device_path,
                                                                   target_ip,
                                                                   target_port,
                                                                   handler_commander_queue,
                                                                   baudrate_AT))
    threads.append(commander_thread)

    for t in threads:
        t.start()


if __name__ == "__main__":
    main()
