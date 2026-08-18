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

Send a message:

```bash
curl -X POST http://127.0.0.1:4310/post/UDP \
  --data 'sink_01:sense_04:23.7'
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
