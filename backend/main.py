from __future__ import annotations

import ast
import json
import socket
from threading import Thread
from xml.etree.ElementTree import Element, SubElement, tostring

from flask import Flask, Response, render_template, request

from database import get_messages, init_db, insert_message, insert_packet

web_app = Flask("udp_web")
ingest_app = Flask("udp_ingest")

INGEST_PORT = 9000
WEB_PORT = 8080


def messages_to_xml(messages) -> bytes:
    root = Element("messages")

    for row in messages:
        item = SubElement(root, "message", id=str(row["id"]))
        SubElement(item, "received_at").text = row["received_at"]
        SubElement(item, "sink_id").text = row["sink_id"] or ""
        SubElement(item, "sense_id").text = row["sense_id"] or ""
        SubElement(item, "msg").text = row["msg"] or ""
        SubElement(item, "timestamp").text = row["timestamp"] or ""
        SubElement(item, "rssi").text = "" if row["rssi"] is None else str(row["rssi"])
        SubElement(item, "first_8_bytes").text = row["first_8_bytes"] or ""
        SubElement(item, "data").text = row["data"] or ""

    return tostring(root, encoding="utf-8", xml_declaration=True)


@web_app.get("/get/UDP")
def show_udp_messages():
    messages = get_messages()

    if request.args.get("format") == "xml":
        return Response(messages_to_xml(messages), mimetype="application/xml")

    return render_template("udp.html", messages=messages)


@ingest_app.post("/post/UDP")
def receive_udp_message():
    body = request.get_data(as_text=True).strip()

    if body.startswith("{"):
        try:
            save_packet_payload(body)
            return Response("OK\n", status=200, mimetype="text/plain")
        except (ValueError, SyntaxError, TypeError) as exc:
            return Response(f"Invalid packet: {exc}\n", status=400, mimetype="text/plain")

    try:
        sink_id, sense_id, msg = body.split(":", 2)
    except ValueError:
        return Response(
            "Invalid legacy message: expected sink_id:sense_id:msg\n",
            status=400,
            mimetype="text/plain",
        )

    insert_message(sink_id, sense_id, msg)
    return Response("OK\n", status=200, mimetype="text/plain")


def save_packet_payload(body: str) -> dict:
    payload = parse_packet_payload(body)
    insert_packet(
        payload["timestamp"],
        payload["rssi"],
        payload["first_8_bytes"],
        payload["data"],
    )
    print(
        {
            "timestamp": payload["timestamp"],
            "rssi": payload["rssi"],
            "data": payload["data"],
        },
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

    timestamp = payload.get("timestamp")
    first_8_bytes = payload.get("first_8_bytes")
    data = payload.get("data")

    if not isinstance(timestamp, str) or not timestamp:
        raise ValueError("timestamp must be a non-empty string")
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError("data must be a list of hex byte strings")
    if first_8_bytes is None:
        first_8_bytes = " ".join(data[:8])
    elif not isinstance(first_8_bytes, str) or not first_8_bytes:
        raise ValueError("first_8_bytes must be a non-empty string")

    try:
        rssi = int(payload["rssi"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("rssi must be an integer") from exc

    return {
        "timestamp": timestamp,
        "rssi": rssi,
        "first_8_bytes": first_8_bytes,
        "data": data,
    }


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
            body = data.decode("utf-8", errors="replace").strip()
            try:
                save_packet_payload(body)
            except (ValueError, SyntaxError, TypeError) as exc:
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
