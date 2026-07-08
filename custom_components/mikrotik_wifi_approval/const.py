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

SERVICE_APPROVE = "approve"
SERVICE_REJECT = "reject"
SERVICE_DISCONNECT = "disconnect"
SERVICE_MAKE_STATIC = "make_static"

EVENT_NEW_DEVICE = "mikrotik_wifi_new_device"

REST_IDENTITY = "/rest/system/identity"
REST_WIFI_ACCESS_LIST = "/rest/interface/wifi/access-list"
REST_DHCP_LEASE = "/rest/ip/dhcp-server/lease"
REST_WIFI_REGISTRATION = "/rest/interface/wifi/registration-table"

PLATFORMS: list[str] = []