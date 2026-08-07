#include <stdint.h>

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>
#include <nrf_modem_at.h>
#include <zephyr/logging/log.h>

#include "dect_radio.h"

LOG_MODULE_REGISTER(sense_main, LOG_LEVEL_INF);

int main(void)
{
	printk("Starting DECT\n");
	int err;
	uint32_t counter = 0;

	const struct dect_radio_config radio_config = {
		.network_id = CONFIG_NETWORK_ID,
		.carrier = CONFIG_CARRIER,
		.mcs = CONFIG_MCS,
		.tx_power = CONFIG_TX_POWER,
	};
	printk("Initiating DECT\n");
	err = dect_radio_init(&radio_config);

	char fw_version[128];

	err = nrf_modem_at_cmd(
		fw_version,
		sizeof(fw_version),
		"AT+CGMR"
	);

	LOG_INF("Modem FW: %s", fw_version);


	if (err != 0) {
		printk("DECT init failed: %d\n", err);
		return err;
	}

	printk("DECT sense started\n");

	while (1) {
		printk("sense loop");
		uint8_t payload[8] = {
			'S',
			'E',
			'N',
			'S',
			(uint8_t)(counter >> 24),
			(uint8_t)(counter >> 16),
			(uint8_t)(counter >> 8),
			(uint8_t)counter,
		};

		err = dect_radio_send(payload, sizeof(payload));

		if (err != 0) {
			printk("DECT TX failed: %d\n", err);
		} else {
			printk("DECT TX: %u\n", counter);
		}

		counter++;

		k_sleep(K_SECONDS(2));
	}

	return 0;
}