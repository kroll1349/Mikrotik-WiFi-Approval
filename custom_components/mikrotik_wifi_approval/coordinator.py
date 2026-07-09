"""Data update coordinator for MikroTik WiFi Approval."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import MikrotikApiClient
from .const import (
    ATTR_COMMENT,
    ATTR_INTERFACE,
    ATTR_IP,
    ATTR_MAC,
    ATTR_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_NEW_DEVICE,
)

_LOGGER = logging.getLogger(__name__)


class MikrotikWifiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll RouterOS and detect new/unapproved WiFi clients."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: MikrotikApiClient,
    ) -> None:
        """Initialize the coordinator."""

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

        self.api = api

        # MAC addresses we have already notified about, so we don't spam
        # the event bus on every poll while a device is still pending.
        self._known_pending: set[str] = set()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch registration table + access list and diff them."""

        registration = await self.api.registration_table()
        access_list = await self.api.get_access_list()

        decided_macs = {
            entry.get("mac-address", "").lower()
            for entry in access_list
            if entry.get("mac-address")
        }

        pending: list[dict[str, Any]] = []
        seen_macs: set[str] = set()

        for entry in registration:
            mac = entry.get("mac-address", "")

            if not mac:
                continue

            mac_lower = mac.lower()
            seen_macs.add(mac_lower)

            if mac_lower in decided_macs:
                continue

            pending.append(
                {
                    ATTR_MAC: mac,
                    ATTR_INTERFACE: entry.get("interface"),
                    ATTR_NAME: entry.get("comment") or entry.get("interface"),
                }
            )

            if mac_lower not in self._known_pending:
                self._known_pending.add(mac_lower)

                self.hass.bus.async_fire(
                    EVENT_NEW_DEVICE,
                    {
                        ATTR_MAC: mac,
                        ATTR_INTERFACE: entry.get("interface"),
                        ATTR_IP: entry.get("last-ip"),
                        ATTR_COMMENT: entry.get("comment", ""),
                    },
                )

        # Forget devices that are no longer pending (approved, rejected,
        # or disconnected), so a future reappearance fires the event again.
        self._known_pending &= seen_macs

        return {
            "pending": pending,
            "registration": registration,
            "access_list": access_list,
        }
