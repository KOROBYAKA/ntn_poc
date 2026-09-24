ARG BASE_IMAGE=python:3.13-alpine3.23

# =========================
# Builder
# =========================
FROM $BASE_IMAGE AS builder

RUN addgroup -g 1000 wirepas \
    && adduser \
        --disabled-password \
        -u 1000 \
        -G wirepas \
        wirepas

# Build dependencies for PyGObject
RUN apk add --no-cache \
        build-base \
        cairo-dev \
        gobject-introspection-dev \
        glib-dev

USER wirepas
WORKDIR /home/wirepas

# Install Python dependencies into /home/wirepas/.local
RUN pip3 install --no-cache-dir --user \
        pyserial==3.5 \
        pydbus \
        "PyGObject~=3.0" \
        ntplib

# Sanity check
RUN python3 -c "\
import serial; \
import ntplib; \
from pydbus import connect; \
from gi.repository import GLib; \
print('Python dependencies OK'); \
print(serial.Serial)"


# =========================
# Runner
# =========================
FROM $BASE_IMAGE AS runner

RUN addgroup -g 1000 wirepas \
    && adduser \
        --disabled-password \
        -u 1000 \
        -G wirepas \
        wirepas

# Runtime dependencies for PyGObject / Gio
RUN apk add --no-cache \
        glib \
        gobject-introspection \
        libstdc++ \
        tzdata

USER wirepas

ENV PATH="/home/wirepas/.local/bin:${PATH}"
ENV PYTHONPATH="/home/wirepas/.local/lib/python3.13/site-packages"
ENV PYTHONUNBUFFERED=1

WORKDIR /home/wirepas/ntn_gateway

COPY --from=builder \
    --chown=wirepas:wirepas \
    /home/wirepas/.local \
    /home/wirepas/.local

COPY --chown=wirepas:wirepas \
    main.py \
    at_commander.py \
    dbus_connector.py \
    ./

# Verify final image too
RUN python3 -c "\
import serial; \
import ntplib; \
from pydbus import connect; \
from gi.repository import GLib; \
print('Runtime dependencies OK')"

CMD ["python3", "main.py"]