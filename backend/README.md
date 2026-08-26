# UDP backend PoC

Install:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run:

```bash
python main.py
```

This starts:

```text
HTTP packet ingest: http://127.0.0.1:9000/post/UDP
UDP packet ingest:  127.0.0.1:9000
HTML table:         http://127.0.0.1:8080/get/UDP
```

Send a message:

```bash
curl -X POST http://127.0.0.1:9000/post/UDP \
  --data 'sink_01:sense_04:23.7'
```

Send a receiver packet:

```bash
curl -X POST http://127.0.0.1:9000/post/UDP \
  -H 'Content-Type: application/json' \
  --data '{"timestamp":"2026-08-26T15:26:35.396356+00:00","rssi":-151,"data":["53","45","4e","53","00","00","b4","1a"]}'
```

HTML table:

```text
http://127.0.0.1/get/UDP
```

XML:

```text
http://127.0.0.1/get/UDP?format=xml
```

On Linux, binding to port 80 may require elevated privileges or a capability. For local development, changing port 80 to 8080 is usually simpler.
