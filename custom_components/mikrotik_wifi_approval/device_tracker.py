"""Device tracker platform for MikroTik WiFi Approval."""

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
    """Set up device_tracker entities for known WiFi clients."""

    coordinator: MikrotikWifiCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_macs: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        registration = coordinator.data.get("registration", [])
        access_list = coordinator.data.get("access_list", [])

        # Un dispozitiv merită o entitate din momentul în care apare fie
        # ca fiind conectat acum (registration-table), fie ca fiind deja
        # decis (access-list) - altfel un device aprobat dar deconectat
        # ar dispărea din HA.
        all_macs = {
            entry_row.get("mac-address", "").lower()
            for entry_row in registration
            if entry_row.get("mac-address")
        } | {
            entry_row.get("mac-address", "").lower()
            for entry_row in access_list
            if entry_row.get("mac-address")
        }

        new_entities = [
            MikrotikDeviceTracker(coordinator, entry, mac)
            for mac in all_macs
            if mac not in known_macs
        ]

        if new_entities:
            known_macs.update(mac.mac_address_lower for mac in new_entities)
            async_add_entities(new_entities)

    _add_new_entities()
    coordinator.async_add_listener(_add_new_entities)


class MikrotikDeviceTracker(CoordinatorEntity[MikrotikWifiCoordinator], ScannerEntity):
    """Track a single WiFi client seen in the registration-table."""

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

    @property
    def _registration_entry(self) -> dict[str, Any] | None:
        """Return the live registration-table row for this MAC, if connected."""

        for row in self.coordinator.data.get("registration", []):
            if row.get("mac-address", "").lower() == self.mac_address_lower:
                return row
        return None

    @property
    def _access_list_entry(self) -> dict[str, Any] | None:
        """Return the access-list row for this MAC, if it has been decided."""

        for row in self.coordinator.data.get("access_list", []):
            if row.get("mac-address", "").lower() == self.mac_address_lower:
                return row
        return None

    @property
    def name(self) -> str:
        """Prefer the access-list comment, then registration comment, then MAC."""

        access = self._access_list_entry
        reg = self._registration_entry

        comment = (access or {}).get("comment") or (reg or {}).get("comment")

        return comment or self.mac_address_lower

    @property
    def is_connected(self) -> bool:
        """A device is 'home' only while it's live in the registration-table."""

        return self._registration_entry is not None

    @property
    def mac_address(self) -> str:
        return self.mac_address_lower

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        reg = self._registration_entry or {}
        access = self._access_list_entry or {}

        return {
            "interface": reg.get("interface"),  # ac2 / ax2
            "signal_strength": reg.get("signal-strength"),
            "tx_rate": reg.get("tx-rate"),
            "rx_rate": reg.get("rx-rate"),
            "uptime": reg.get("uptime"),
            "last_ip": reg.get("last-ip"),
            "approved": access.get("action") == "accept",
        }
