"""Sensor platform for MikroTik WiFi Approval."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import ATTR_INTERFACE, ATTR_MAC, ATTR_NAME, DOMAIN
from .coordinator import MikrotikWifiCoordinator


def _format_uptime(seconds: float) -> str:
    """Format a duration in seconds as a short MikroTik-style string."""

    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    if days:
        return f"{days}d{hours}h{minutes}m"
    if hours:
        return f"{hours}h{minutes}m"
    if minutes:
        return f"{minutes}m{seconds}s"
    return f"{seconds}s"


def _is_randomized_mac(mac: str) -> bool:
    """Return True if the MAC has the 'locally administered' bit set.

    This is the standard signature of a privacy/random WiFi MAC (iOS,
    modern Android). Note plenty of *wired* virtual NICs (Docker,
    Proxmox) also use locally-administered addresses on purpose, so
    this check alone isn't enough to hide a device - it's only used
    together with "no known name" below.
    """

    try:
        first_octet = int(mac.split(":")[0], 16)
    except (ValueError, IndexError):
        return False

    return bool(first_octet & 0x02)


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
        bridge_hosts = data.get("bridge_hosts", [])
        lan_first_seen = data.get("lan_first_seen", {})

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
        # Only keep the physical-port entries (ether1, ether3, ...) -
        # the bridge host table also lists the bridge's own virtual
        # interfaces, which aren't useful here.
        port_by_mac = {
            e.get("mac-address", "").lower(): e.get("on-interface")
            for e in bridge_hosts
            if e.get("mac-address")
            and (e.get("on-interface") or "").lower().startswith("ether")
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
                    "signal": entry_row.get("signal"),
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

            known_name = access.get("comment") or lease.get("host-name")

            if _is_randomized_mac(arp_entry.get("mac-address", "")) and not known_name:
                # Foarte probabil un telefon/tabletă cu MAC privat, ieșit
                # temporar din registration-table (roaming/idle) - nu are
                # niciun identificator persistent, deci nu-l mai afișăm
                # ca "LAN" fals; la reconectare pe WiFi revine normal.
                continue

            port = port_by_mac.get(mac_lower)
            first_seen = lan_first_seen.get(mac_lower)
            uptime = None

            if first_seen:
                try:
                    elapsed = (
                        dt_util.utcnow() - dt_util.parse_datetime(first_seen)
                    ).total_seconds()
                    uptime = _format_uptime(elapsed)
                except (TypeError, ValueError):
                    uptime = None

            rows.append(
                {
                    ATTR_NAME: (
                        known_name
                        or arp_entry.get("mac-address")
                    ),
                    ATTR_MAC: arp_entry.get("mac-address"),
                    ATTR_INTERFACE: port or arp_entry.get("interface"),
                    "ip": arp_entry.get("address") or lease.get("address"),
                    "uptime": uptime,
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
