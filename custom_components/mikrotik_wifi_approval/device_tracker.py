"""Device tracker platform for MikroTik WiFi Approval.

Covers WiFi clients (via the wifi registration-table, same source used
for approval) AND wired/LAN clients (via ARP + DHCP leases), so every
device that has ever shown up on the router - WiFi or Ethernet - gets
an entity.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import ScannerEntity, SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MikrotikWifiCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up device_tracker entities for every known client (WiFi + LAN)."""

    coordinator: MikrotikWifiCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_macs: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        data = coordinator.data

        all_macs: set[str] = set()
        for source_key in ("registration", "access_list", "leases", "arp"):
            for row in data.get(source_key, []):
                mac = row.get("mac-address", "")
                if mac:
                    all_macs.add(mac.lower())

        new_entities = [
            MikrotikDeviceTracker(coordinator, entry, mac)
            for mac in all_macs
            if mac not in known_macs
        ]

        if new_entities:
            known_macs.update(e.mac_address_lower for e in new_entities)
            async_add_entities(new_entities)

    _add_new_entities()
    coordinator.async_add_listener(_add_new_entities)


class MikrotikDeviceTracker(CoordinatorEntity[MikrotikWifiCoordinator], ScannerEntity):
    """Track a single client, wireless or wired."""

    _attr_has_entity_name = True
    _attr_source_type = SourceType.ROUTER

    def __init__(
        self,
        coordinator: MikrotikWifiCoordinator,
        entry: ConfigEntry,
        mac: str,
    ) -> None:
        """Initialize the tracker for a single MAC address."""

        super().__init__(coordinator)

        self.mac_address_lower = mac
        self._attr_unique_id = f"{entry.entry_id}_{mac}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "MikroTik",
        }

    # ----- lookups across the four data sources -----

    def _find(self, source_key: str) -> dict[str, Any] | None:
        for row in self.coordinator.data.get(source_key, []):
            if row.get("mac-address", "").lower() == self.mac_address_lower:
                return row
        return None

    @property
    def _registration_entry(self) -> dict[str, Any] | None:
        return self._find("registration")

    @property
    def _access_list_entry(self) -> dict[str, Any] | None:
        return self._find("access_list")

    @property
    def _lease_entry(self) -> dict[str, Any] | None:
        return self._find("leases")

    @property
    def _arp_entry(self) -> dict[str, Any] | None:
        return self._find("arp")

    # ----- entity properties -----

    @property
    def name(self) -> str:
        access = self._access_list_entry or {}
        reg = self._registration_entry or {}
        lease = self._lease_entry or {}

        return (
            access.get("comment")
            or reg.get("comment")
            or lease.get("host-name")
            or lease.get("comment")
            or self.mac_address_lower
        )

    @property
    def is_connected(self) -> bool:
        """Home if seen live on WiFi (registration-table) or resolvable
        right now on the LAN (a 'complete', non-stale ARP entry).

        A DHCP lease alone is NOT enough - leases persist for the full
        lease time even after the device goes offline, so relying on
        them would make everything look permanently 'home'.
        """

        if self._registration_entry is not None:
            return True

        arp = self._arp_entry
        if arp is not None and arp.get("complete") in (True, "true"):
            return True

        return False

    @property
    def mac_address(self) -> str:
        return self.mac_address_lower

    @property
    def ip_address(self) -> str | None:
        reg = self._registration_entry or {}
        arp = self._arp_entry or {}
        lease = self._lease_entry or {}

        return reg.get("last-ip") or arp.get("address") or lease.get("address")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        reg = self._registration_entry or {}
        access = self._access_list_entry or {}
        arp = self._arp_entry or {}
        lease = self._lease_entry or {}

        connection = "wifi" if reg else ("lan" if arp or lease else "unknown")

        return {
            "connection": connection,
            "interface": reg.get("interface") or arp.get("interface"),  # ac2/ax2 sau ether-ul de LAN
            "signal_strength": reg.get("signal-strength"),
            "tx_rate": reg.get("tx-rate"),
            "rx_rate": reg.get("rx-rate"),
            "uptime": reg.get("uptime"),
            "ip_address": self.ip_address,
            "hostname": lease.get("host-name"),
            "approved": access.get("action") == "accept",
        }
