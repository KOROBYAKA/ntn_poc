import queue

def handle_message(message):
    #!TODO
    pass




def message_handler(rx_queue: queue.Queue, tx_queue: queue.Queue):
    print("Starting the message handler")
    while True:
        message = rx_queue.get()
        #message = handle_message(message)
        print(f"handle_message::{message}")
        #!TODO: Add some processing logic/analysis later

        tx_queue.put(message)
        print(f"handle_message::msg_put()")