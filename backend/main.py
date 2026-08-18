from threading import Thread
from xml.etree.ElementTree import Element, SubElement, tostring

from flask import Flask, Response, render_template, request

from database import get_messages, init_db, insert_message

web_app = Flask("udp_web")
ingest_app = Flask("udp_ingest")


def messages_to_xml(messages) -> bytes:
    root = Element("messages")

    for row in messages:
        item = SubElement(root, "message", id=str(row["id"]))
        SubElement(item, "received_at").text = row["received_at"]
        SubElement(item, "sink_id").text = row["sink_id"]
        SubElement(item, "sense_id").text = row["sense_id"]
        SubElement(item, "msg").text = row["msg"]

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
    sink_id, sense_id, msg = body.split(":", 2)
    insert_message(sink_id, sense_id, msg)
    return Response("OK\n", status=200, mimetype="text/plain")


def run_ingest_server() -> None:
    ingest_app.run(
        host="0.0.0.0",
        port=4310,
        threaded=True,
        use_reloader=False,
    )


if __name__ == "__main__":
    init_db()

    Thread(target=run_ingest_server, daemon=True).start()

    web_app.run(
        host="0.0.0.0",
        port=8080,
        threaded=True,
        use_reloader=False,
    )
