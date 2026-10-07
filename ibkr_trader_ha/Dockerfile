FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION=0.1.0

LABEL     io.hass.name="IBKR Trader HA"     io.hass.description="Autonomous Interactive Brokers trading application"     io.hass.type="app"     io.hass.version="$BUILD_VERSION"

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY run.sh ./

RUN apk add --no-cache python3 py3-pip     && pip3 install --no-cache-dir --break-system-packages .     && chmod a+x /app/run.sh

CMD ["/app/run.sh"]
