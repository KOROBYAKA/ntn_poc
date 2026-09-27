from __future__ import annotations

import ast
import json
import socket
from datetime import datetime, timezone
from threading import Thread
from xml.etree.ElementTree import Element, SubElement, tostring

from flask import Flask, Response, render_template, request

from database import get_packets, init_db, insert_packet

web_app = Flask("udp_web")
ingest_app = Flask("udp_ingest")

INGEST_PORT = 9000
WEB_PORT = 8080


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def epoch_ms_to_utc_iso(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(
        timestamp_ms / 1000,
        tz=timezone.utc,
    ).isoformat(timespec="milliseconds")


def first_16_bytes(payload_hex: str) -> str:
    compact = payload_hex.replace(" ", "")[:32]
    return " ".join(compact[i:i + 2] for i in range(0, len(compact), 2))


def packets_to_xml(packets) -> bytes:
    root = Element("packets")

    for row in packets:
        item = SubElement(root, "packet", id=str(row["id"]))
        SubElement(item, "src").text = str(row["src"])
        SubElement(item, "gw_timestamp").text = row["gw_timestamp"] or ""
        SubElement(item, "travel_time").text = str(row["travel_time"])
        SubElement(item, "backend_timestamp").text = row["backend_timestamp"] or ""
        SubElement(item, "payload").text = row["payload"] or ""

    return tostring(root, encoding="utf-8", xml_declaration=True)


@web_app.get("/get/UDP")
def show_udp_packets():
    packets = get_packets()

    if request.args.get("format") == "xml":
        return Response(packets_to_xml(packets), mimetype="application/xml")

    return render_template("udp.html", packets=packets)


@ingest_app.post("/post/UDP")
def receive_udp_message():
    backend_timestamp = utc_now_iso()
    body = request.get_data(as_text=True).strip()

    try:
        save_packet_payload(body, backend_timestamp)
    except (ValueError, SyntaxError, TypeError, KeyError) as exc:
        return Response(f"Invalid packet: {exc}\n", status=400, mimetype="text/plain")

    return Response("OK\n", status=200, mimetype="text/plain")


def save_packet_payload(body: str, backend_timestamp: str) -> dict:
    payload = parse_packet_payload(body)

    src = int(payload["src"])
    gw_timestamp = epoch_ms_to_utc_iso(int(payload["gw_rx_timestamp"]))
    travel_time = int(payload["travel_time"])
    payload_16b = first_16_bytes(str(payload["data"]))

    insert_packet(
        src=src,
        gw_timestamp=gw_timestamp,
        travel_time=travel_time,
        backend_timestamp=backend_timestamp,
        payload=payload_16b,
    )

    print(
        f"src={src} "
        f"gw_timestamp={gw_timestamp} "
        f"travel_time={travel_time} "
        f"backend_timestamp={backend_timestamp} "
        f"payload={payload_16b}",
        flush=True,
    )

    return payload


def parse_packet_payload(body: str) -> dict:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = ast.literal_eval(body)

    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")

    return payload


def run_ingest_server() -> None:
    ingest_app.run(
        host="0.0.0.0",
        port=INGEST_PORT,
        threaded=True,
        use_reloader=False,
    )


def run_udp_packet_server() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0", INGEST_PORT))
        print(f"UDP packet ingest listening on 0.0.0.0:{INGEST_PORT}", flush=True)

        while True:
            data, address = sock.recvfrom(65535)
            backend_timestamp = utc_now_iso()

            body = data.decode("utf-8", errors="replace").strip()

            try:
                save_packet_payload(body, backend_timestamp)
            except (ValueError, SyntaxError, TypeError, KeyError) as exc:
                print(f"Invalid UDP packet from {address}: {exc}", flush=True)


if __name__ == "__main__":
    init_db()

    Thread(target=run_ingest_server, daemon=True).start()
    Thread(target=run_udp_packet_server, daemon=True).start()

    web_app.run(
        host="0.0.0.0",
        port=WEB_PORT,
        threaded=True,
        use_reloader=False,
    )
