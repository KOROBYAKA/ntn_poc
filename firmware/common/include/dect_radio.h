#ifndef DECT_RADIO_H_
#define DECT_RADIO_H_

#include <stddef.h>
#include <stdint.h>

#define DECT_RADIO_MAX_PAYLOAD_SIZE 32U

struct dect_radio_config {
	uint32_t network_id;
	uint16_t carrier;
	uint8_t mcs;
	uint8_t tx_power;
};

typedef void (*dect_radio_rx_callback_t)(
	const uint8_t *data,
	size_t len,
	int16_t rssi_2
);

int dect_radio_init(const struct dect_radio_config *config);
int dect_radio_send(const uint8_t *data, size_t len);
int dect_radio_start_rx(dect_radio_rx_callback_t callback);

uint16_t dect_radio_device_id_get(void);

#endif