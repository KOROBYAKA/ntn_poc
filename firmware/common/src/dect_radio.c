#include "dect_radio.h"

#include <errno.h>
#include <stdbool.h>

#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/drivers/hwinfo.h>

#include <modem/nrf_modem_lib.h>
#include <nrf_modem_dect_phy.h>

LOG_MODULE_REGISTER(dect_radio);

#define DECT_RADIO_TX_HANDLE 1U
#define DECT_RADIO_RX_HANDLE 2U

#define DECT_RADIO_RX_WINDOW_S 60U


/*
 * PHY header type 1.
 *
 * Field order differs from the DECT specification due
 * to endianness. Same layout as Nordic Hello DECT sample.
 */
struct phy_ctrl_field_common {
	uint32_t packet_length : 4;
	uint32_t packet_length_type : 1;
	uint32_t header_format : 3;

	uint32_t short_network_id : 8;
	uint32_t transmitter_id_hi : 8;
	uint32_t transmitter_id_lo : 8;

	uint32_t df_mcs : 3;
	uint32_t reserved : 1;
	uint32_t transmit_power : 4;
	uint32_t pad : 24;
};


/*
 * Synchronization objects.
 */
K_SEM_DEFINE(init_sem, 0, 1);
K_SEM_DEFINE(tx_sem, 0, 1);
K_SEM_DEFINE(rx_sem, 0, 1);

K_MUTEX_DEFINE(tx_mutex);


static struct dect_radio_config radio_config;

static uint16_t device_id;
static bool radio_initialized;

static int init_status;
static int tx_status;
static int rx_status;

static dect_radio_rx_callback_t rx_callback;


/* -------------------------------------------------------------------------
 * DECT PHY callbacks
 * -------------------------------------------------------------------------
 */

static void on_init(
	const uint64_t *time,
	int16_t temp,
	enum nrf_modem_dect_phy_err err,
	const struct nrf_modem_dect_phy_modem_cfg *cfg)
{
	(void)time;

	init_status = err;

	if (err != NRF_MODEM_DECT_PHY_SUCCESS) {
		LOG_ERR(
			"DECT PHY init failed: err=%d temp=%d",
			err,
			temp
		);
	} else {
		LOG_INF(
			"DECT PHY init complete: temp=%d limit=%d",
			temp,
			cfg->temperature_limit
		);
	}

	k_sem_give(&init_sem);
}


static void on_deinit(
	const uint64_t *time,
	enum nrf_modem_dect_phy_err err)
{
	(void)time;
	(void)err;
}


static void on_operation_complete(
	const uint64_t *time,
	int16_t temperature,
	enum nrf_modem_dect_phy_err err,
	uint32_t handle)
{
	(void)time;
	(void)temperature;

	if (handle == DECT_RADIO_TX_HANDLE) {
		tx_status = err;
		k_sem_give(&tx_sem);
		return;
	}

	if (handle == DECT_RADIO_RX_HANDLE) {
		rx_status = err;
		k_sem_give(&rx_sem);
	}
}


static void on_rx_stop(
	const uint64_t *time,
	enum nrf_modem_dect_phy_err err,
	uint32_t handle)
{
	(void)time;
	(void)err;
	(void)handle;
}


static void on_pcc(
	const uint64_t *time,
	const struct nrf_modem_dect_phy_rx_pcc_status *status,
	const union nrf_modem_dect_phy_hdr *hdr)
{
	(void)time;
	(void)status;
	(void)hdr;
}


static void on_pcc_crc_err(
	const uint64_t *time,
	const struct nrf_modem_dect_phy_rx_pcc_crc_failure *failure)
{
	(void)time;
	(void)failure;
}


static void on_pdc(
	const uint64_t *time,
	const struct nrf_modem_dect_phy_rx_pdc_status *status,
	const void *data,
	uint32_t len)
{
	(void)time;

	if (rx_callback != NULL) {
		rx_callback(
			(const uint8_t *)data,
			(size_t)len,
			status->rssi_2
		);
	}
}


static void on_pdc_crc_err(
	const uint64_t *time,
	const struct nrf_modem_dect_phy_rx_pdc_crc_failure *failure)
{
	(void)time;
	(void)failure;
}


static void on_rssi(
	const uint64_t *time,
	const struct nrf_modem_dect_phy_rssi_meas *status)
{
	(void)time;
	(void)status;
}


static void on_link_config(
	const uint64_t *time,
	enum nrf_modem_dect_phy_err err)
{
	(void)time;
	(void)err;
}


static void on_time_get(
	const uint64_t *time,
	enum nrf_modem_dect_phy_err err)
{
	(void)time;
	(void)err;
}


static void on_capability_get(
	const uint64_t *time,
	enum nrf_modem_dect_phy_err err,
	const struct nrf_modem_dect_phy_capability *capability)
{
	(void)time;
	(void)err;
	(void)capability;
}


/*
 * NCS 2.7.0 DECT PHY uses callback table instead
 * of the event dispatcher used by newer SDKs.
 */
static struct nrf_modem_dect_phy_callbacks dect_callbacks = {
	.init = on_init,
	.deinit = on_deinit,
	.op_complete = on_operation_complete,
	.rx_stop = on_rx_stop,
	.pcc = on_pcc,
	.pcc_crc_err = on_pcc_crc_err,
	.pdc = on_pdc,
	.pdc_crc_err = on_pdc_crc_err,
	.rssi = on_rssi,
	.link_config = on_link_config,
	.time_get = on_time_get,
	.capability_get = on_capability_get,
};


static struct nrf_modem_dect_phy_init_params dect_init_params = {
	.harq_rx_expiry_time_us = 5000000,
	.harq_rx_process_count = 4,
};


/* -------------------------------------------------------------------------
 * Internal helpers
 * -------------------------------------------------------------------------
 */

static int wait_for_init_operation(void)
{
	k_sem_take(&init_sem, K_FOREVER);

	return init_status;
}


/* -------------------------------------------------------------------------
 * Public API
 * -------------------------------------------------------------------------
 */

int dect_radio_init(const struct dect_radio_config *config)
{
	int err;

	if (config == NULL) {
		return -EINVAL;
	}

	if (radio_initialized) {
		return -EALREADY;
	}

	radio_config = *config;


	err = nrf_modem_lib_init();

	if (err != 0) {
		LOG_ERR(
			"Modem library initialization failed: %d",
			err
		);

		return err;
	}


	/*
	 * NCS 2.7.0 requires callbacks to be registered
	 * before nrf_modem_dect_phy_init().
	 */
	err = nrf_modem_dect_phy_callback_set(&dect_callbacks);

	if (err != 0) {
		LOG_ERR(
			"DECT callback setup failed: %d",
			err
		);

		return err;
	}


	k_sem_reset(&init_sem);
	init_status = 0;


	err = nrf_modem_dect_phy_init(&dect_init_params);

	if (err != 0) {
		LOG_ERR(
			"DECT PHY init request failed: %d",
			err
		);

		return err;
	}


	err = wait_for_init_operation();

	if (err != NRF_MODEM_DECT_PHY_SUCCESS) {
		LOG_ERR(
			"DECT PHY initialization failed: %d",
			err
		);

		return -EIO;
	}


	err = hwinfo_get_device_id(
		(uint8_t *)&device_id,
		sizeof(device_id)
	);

	if (err < 0) {
		LOG_ERR(
			"Device ID read failed: %d",
			err
		);

		return err;
	}


	radio_initialized = true;

	LOG_INF(
		"DECT PHY initialized, device ID: %u",
		device_id
	);

	return 0;
}


int dect_radio_send(
	const uint8_t *data,
	size_t len)
{
	int err;

	if (!radio_initialized) {
		return -EACCES;
	}

	if (data == NULL) {
		return -EINVAL;
	}

	if ((len == 0U) ||
	    (len > DECT_RADIO_MAX_PAYLOAD_SIZE)) {
		return -EMSGSIZE;
	}


	k_mutex_lock(&tx_mutex, K_FOREVER);

	k_sem_reset(&tx_sem);
	tx_status = 0;


	struct phy_ctrl_field_common header = {
		.header_format = 0x0,
		.packet_length_type = 0x0,
		.packet_length = 0x01,

		.short_network_id =
			radio_config.network_id & 0xff,

		.transmitter_id_hi =
			device_id >> 8,

		.transmitter_id_lo =
			device_id & 0xff,

		.transmit_power =
			radio_config.tx_power,

		.reserved = 0,

		.df_mcs =
			radio_config.mcs,
	};


	struct nrf_modem_dect_phy_tx_params tx_params = {
		.start_time = 0,

		.handle =
			DECT_RADIO_TX_HANDLE,

		.network_id =
			radio_config.network_id,

		.phy_type = 0,

		.lbt_rssi_threshold_max = 0,

		.carrier =
			radio_config.carrier,

		.lbt_period =
			NRF_MODEM_DECT_LBT_PERIOD_MAX,

		.phy_header =
			(union nrf_modem_dect_phy_hdr *)&header,

		.data =
			(void *)data,

		.data_size =
			len,
	};


	err = nrf_modem_dect_phy_tx(&tx_params);

	if (err != 0) {
		LOG_ERR(
			"DECT TX request failed: %d",
			err
		);

		k_mutex_unlock(&tx_mutex);

		return err;
	}


	k_sem_take(&tx_sem, K_FOREVER);


	if (tx_status != NRF_MODEM_DECT_PHY_SUCCESS) {
		LOG_ERR(
			"DECT TX operation failed: %d",
			tx_status
		);

		k_mutex_unlock(&tx_mutex);

		return -EIO;
	}


	k_mutex_unlock(&tx_mutex);

	return 0;
}


int dect_radio_start_rx(
	dect_radio_rx_callback_t callback)
{
	int err;

	if (!radio_initialized) {
		return -EACCES;
	}

	if (callback == NULL) {
		return -EINVAL;
	}


	rx_callback = callback;

	k_sem_reset(&rx_sem);
	rx_status = 0;


	struct nrf_modem_dect_phy_rx_params rx_params = {
		.start_time = 0,

		.handle =
			DECT_RADIO_RX_HANDLE,

		.network_id =
			radio_config.network_id,

		.mode =
			NRF_MODEM_DECT_PHY_RX_MODE_CONTINUOUS,

		.rssi_interval =
			NRF_MODEM_DECT_PHY_RSSI_INTERVAL_OFF,

		.link_id =
			NRF_MODEM_DECT_PHY_LINK_UNSPECIFIED,

		.rssi_level = -60,

		.carrier =
			radio_config.carrier,

		.duration = (uint32_t)(
			(uint64_t)DECT_RADIO_RX_WINDOW_S *
			MSEC_PER_SEC *
			NRF_MODEM_DECT_MODEM_TIME_TICK_RATE_KHZ
		),

		.filter.short_network_id =
			radio_config.network_id & 0xff,

		.filter.is_short_network_id_used = 1,

		.filter.receiver_identity = 0,
	};


	err = nrf_modem_dect_phy_rx(&rx_params);

	if (err != 0) {
		LOG_ERR(
			"DECT RX request failed: %d",
			err
		);

		return err;
	}


	k_sem_take(&rx_sem, K_FOREVER);


	if (rx_status != NRF_MODEM_DECT_PHY_SUCCESS) {
		LOG_ERR(
			"DECT RX operation failed: %d",
			rx_status
		);

		return -EIO;
	}


	return 0;
}


uint16_t dect_radio_device_id_get(void)
{
	return device_id;
}