import time
import ntplib

NTP_SERVER = ""
SAMPLES = 20
TIMEOUT = 2.0


def main():
    client = ntplib.NTPClient()
    samples = []

    for i in range(SAMPLES):
        response = client.request(
            NTP_SERVER,
            version=4,
            timeout=TIMEOUT,
        )

        samples.append(response)

        print(
            f"{i:02d}: "
            f"delay={response.delay * 1000:.3f} ms, "
            f"offset={response.offset * 1000:+.3f} ms"
        )

    best = min(samples, key=lambda r: r.delay)

    print(
        f"\nBest sample: "
        f"delay={best.delay * 1000:.3f} ms, "
        f"offset={best.offset * 1000:+.3f} ms"
    )

    current_time = time.clock_gettime(time.CLOCK_REALTIME)
    time.clock_settime(
        time.CLOCK_REALTIME,
        current_time + best.offset,
    )

    print("Clock synchronized.")


if __name__ == "__main__":
    main()
