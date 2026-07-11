"""Sensor platform for MikroTik WiFi Approval."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_INTERFACE, ATTR_MAC, ATTR_NAME, DOMAIN
from .coordinator import MikrotikWifiCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the pending-devices and connected-clients sensors."""

    coordinator: MikrotikWifiCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            PendingDevicesSensor(coordinator, entry),
            ConnectedClientsSensor(coordinator, entry),
        ]
    )


class PendingDevicesSensor(CoordinatorEntity[MikrotikWifiCoordinator], SensorEntity):
    """Number of WiFi devices currently waiting for approval."""

    _attr_has_entity_name = True
    _attr_name = "Pending devices"
    _attr_icon = "mdi:wifi-lock-open"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MikrotikWifiCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""

        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.entry_id}_pending_devices"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "MikroTik",
        }

    @property
    def native_value(self) -> int:
        """Return the number of pending devices."""

        return len(self.coordinator.data.get("pending", []))

    @property
    def extra_state_attributes(self) -> dict:
        """Return MAC/name of each pending device."""

        pending = self.coordinator.data.get("pending", [])

        return {
            "devices": [
                {ATTR_MAC: d[ATTR_MAC], ATTR_NAME: d.get(ATTR_NAME)}
                for d in pending
            ]
        }


class ConnectedClientsSensor(CoordinatorEntity[MikrotikWifiCoordinator], SensorEntity):
    """Simple flat list of every client currently connected - WiFi or LAN.

    One entity, one 'devices' attribute with a row per client:
    name / mac / interface (ac2, ax2, ether3, ...) / ip / uptime / connection.
    No per-device HA entities or device-registry entries are created -
    just data to read in a Lovelace card or template.
    """

    _attr_has_entity_name = True
    _attr_name = "Clienți conectați"
    _attr_icon = "mdi:lan-connect"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: MikrotikWifiCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""

        super().__init__(coordinator)

        self._attr_unique_id = f"{entry.entry_id}_connected_clients"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "MikroTik",
        }

    def _build_rows(self) -> list[dict]:
        data = self.coordinator.data

        registration = data.get("registration", [])
        access_list = data.get("access_list", [])
        leases = data.get("leases", [])
        arp = data.get("arp", [])

        access_by_mac = {
            e.get("mac-address", "").lower(): e
            for e in access_list
            if e.get("mac-address")
        }
        lease_by_mac = {
            e.get("mac-address", "").lower(): e
            for e in leases
            if e.get("mac-address")
        }
        arp_by_mac = {
            e.get("mac-address", "").lower(): e
            for e in arp
            if e.get("mac-address")
        }

        rows: list[dict] = []

        # --- WiFi: everything live in the registration-table ---
        for entry_row in registration:
            mac = entry_row.get("mac-address", "")
            if not mac:
                continue

            mac_lower = mac.lower()
            access = access_by_mac.get(mac_lower, {})
            lease = lease_by_mac.get(mac_lower, {})

            rows.append(
                {
                    ATTR_NAME: (
                        access.get("comment")
                        or entry_row.get("comment")
                        or lease.get("host-name")
                        or mac
                    ),
                    ATTR_MAC: mac,
                    ATTR_INTERFACE: entry_row.get("interface"),
                    "ip": entry_row.get("last-ip") or lease.get("address"),
                    "uptime": entry_row.get("uptime"),
                    "signal": entry_row.get("signal-strength"),
                    "connection": "wifi",
                    "approved": access.get("action") == "accept",
                    "pending": mac_lower not in access_by_mac,
                }
            )

        # --- LAN: resolvable now on ARP, and not already listed via WiFi ---
        wifi_macs = {r["mac"].lower() for r in rows}

        for mac_lower, arp_entry in arp_by_mac.items():
            if mac_lower in wifi_macs:
                continue

            if arp_entry.get("complete") not in (True, "true"):
                continue

            access = access_by_mac.get(mac_lower, {})
            lease = lease_by_mac.get(mac_lower, {})

            rows.append(
                {
                    ATTR_NAME: (
                        access.get("comment")
                        or lease.get("host-name")
                        or arp_entry.get("mac-address")
                    ),
                    ATTR_MAC: arp_entry.get("mac-address"),
                    ATTR_INTERFACE: arp_entry.get("interface"),
                    "ip": arp_entry.get("address") or lease.get("address"),
                    "uptime": None,
                    "signal": None,
                    "connection": "lan",
                    "approved": None,
                    "pending": False,
                }
            )

        return rows

    @property
    def native_value(self) -> int:
        """Return how many clients are currently connected."""

        return len(self._build_rows())

    @property
    def extra_state_attributes(self) -> dict:
        """Return the flat device list."""

        return {"devices": self._build_rows()}
