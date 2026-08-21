import queue
from datetime import datetime, timezone
import re

def handle_message(log_line):
    pattern = r"RSSI2?:?\s*(-?\d+)\s+data:(.+)"
    match = re.search(pattern, log_line)
    if not match:
        return None

    rssi = int(match.group(1))
    raw_hex_tokens = match.group(2).strip().split()
    first_8_tokens = raw_hex_tokens[:8]

    # Joined hex string (e.g., '53 45 4e 53 00 00 00 99')
    first_8_hex = " ".join(first_8_tokens)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rssi": rssi,
        "data": first_8_tokens,  # ['53', '45', '4e', '53', '00', '00', '00', '99']
    }




def message_handler(rx_queue: queue.Queue, tx_queue: queue.Queue):
    print("Starting the message handler")
    while True:
        message = rx_queue.get()
        message = handle_message(message)
        if message is None:
            continue
        print(f"handle_message::{message}")
        #!TODO: Add some processing logic/analysis later

        tx_queue.put(message)
        print(f"handle_message::msg_put()")