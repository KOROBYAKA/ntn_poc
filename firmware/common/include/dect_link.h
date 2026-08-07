#define DECT_LINK_MAGIC          0xDEC7
#define DECT_LINK_VERSION        1
#define DECT_LINK_HEADER_SIZE    12
#define DECT_LINK_BROADCAST_ID   0xffff
#define DATA_LEN_MAX 32

enum dect_link_message_type {
    DECT_LINK_MSG_DATA       = 1,
    DECT_LINK_MSG_ACK        = 2,
    DECT_LINK_MSG_BEACON     = 3,
    DECT_LINK_MSG_JOIN_REQ   = 4,
    DECT_LINK_MSG_JOIN_RESP  = 5,
};