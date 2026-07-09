"""Sensor platform for MikroTik WiFi Approval."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTR_MAC, ATTR_NAME, DOMAIN
from .coordinator import MikrotikWifiCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the pending-devices sensor."""

    coordinator: MikrotikWifiCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([PendingDevicesSensor(coordinator, entry)])


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
