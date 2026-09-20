from at_commander import at_commander
import threading
import time
import queue

def main():

# SETUP AT_COMMANDER thread
    commander_target_device_path = "/dev/pts/4"
    target_ip = "127.0.0.1"
    target_port = 9000
    baudrate_AT = 115200
    commander_thread = threading.Thread(target=at_commander, args=(commander_target_device_path,
                                                                   target_ip,
                                                                   target_port,
                                                                   baudrate_AT))
    commander_thread.start()
    commander_thread.join()

if __name__ == "__main__":
    main()
