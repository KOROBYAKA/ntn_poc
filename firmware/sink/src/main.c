#include <stdint.h>
#include <stddef.h>

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include "dect_radio.h"

static void on_dect_rx(
	const uint8_t *data,
	size_t len,
	int16_t rssi_2)
{
	printk(
		"DECT RX: len=%u, RSSI2=%d, data: ",
		(unsigned int)len,
		rssi_2
	);

	for (size_t i = 0; i < len; i++) {
		printk("%02x ", data[i]);
	}

	printk("\n");
}

int main(void)
{
	int err;

	const struct dect_radio_config radio_config = {
		.network_id = CONFIG_NETWORK_ID,
		.carrier = CONFIG_CARRIER,
		.mcs = CONFIG_MCS,
		.tx_power = CONFIG_TX_POWER,
	};

	printk("Starting DECT sink\n");

	err = dect_radio_init(&radio_config);

	if (err != 0) {
		printk("DECT init failed: %d\n", err);
		return err;
	}

	printk("DECT sink started\n");

	while (1) {
		printk("Starting RX window\n");

		err = dect_radio_start_rx(on_dect_rx);

		if (err != 0) {
			printk("DECT RX failed: %d\n", err);
			k_sleep(K_SECONDS(1));
		}
	}

	return 0;
}