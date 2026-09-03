"""Integration constants."""

DOMAIN = "yandex_transit"
ENDPOINT = "https://yandex.ru/maps/api/masstransit/getStopInfo"
DEFAULT_INTERVAL = 60
DEFAULT_SLEEP_START = "22:00:00"
DEFAULT_SLEEP_END = "06:00:00"
CONF_SLEEP_ENABLED = "sleep_enabled"
CONF_SLEEP_START = "sleep_start"
CONF_SLEEP_END = "sleep_end"
MAX_INTERVAL = 86400
MAX_RESPONSE_BYTES = 2_000_000
REQUEST_TIMEOUT = 20
