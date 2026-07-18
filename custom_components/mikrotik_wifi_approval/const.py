"""Constants for the MikroTik WiFi Approval integration."""

from __future__ import annotations

DOMAIN = "mikrotik_wifi_approval"

MANUFACTURER = "MikroTik"

DEFAULT_NAME = "MikroTik WiFi Approval"

DEFAULT_SCAN_INTERVAL = 5

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_WIFI_SENSOR = "wifi_sensor"

ATTR_MAC = "mac"
ATTR_NAME = "name"
ATTR_COMMENT = "comment"
ATTR_IP = "ip"
ATTR_INTERFACE = "interface"
ATTR_VENDOR = "vendor"

SERVICE_APPROVE = "approve"
SERVICE_REJECT = "reject"
SERVICE_DISCONNECT = "disconnect"
SERVICE_MAKE_STATIC = "make_static"
SERVICE_APPROVE_ALL_CURRENT = "approve_all_current"
SERVICE_ENABLE_STRICT_MODE = "enable_strict_mode"

EVENT_NEW_DEVICE = "mikrotik_wifi_new_device"

REST_IDENTITY = "/rest/system/identity"
REST_WIFI_ACCESS_LIST = "/rest/interface/wifi/access-list"
REST_DHCP_LEASE = "/rest/ip/dhcp-server/lease"
REST_WIFI_REGISTRATION = "/rest/interface/wifi/registration-table"
REST_LOG = "/rest/log"
REST_LOGGING = "/rest/system/logging"

# Comment used to tag the catch-all "reject everyone not explicitly
# approved" rule, so we can always find/re-create it reliably and keep
# it as the LAST rule in the access-list (RouterOS checks rules in order,
# top to bottom).
CATCHALL_COMMENT = "ha_catchall_reject"

# Comment used to tag the /system/logging rule we create so we can
# detect connection attempts that get rejected before ever reaching
# the registration-table.
LOGGING_RULE_COMMENT = "ha_wifi_debug"
LOGGING_TOPICS = "wifi,debug"

PLATFORMS: list[str] = []