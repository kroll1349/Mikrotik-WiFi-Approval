"""Data update coordinator for MikroTik WiFi Approval."""

from __future__ import annotations

import logging
import re
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
    CATCHALL_COMMENT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_NEW_DEVICE,
)

_LOGGER = logging.getLogger(__name__)

MAC_RE = re.compile(r"([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})")

# Heuristics for recognizing a connection-attempt log line. RouterOS
# wording can differ slightly between firmware versions, so this is
# intentionally loose - if it misses lines on your router, share a
# sample log line so the pattern can be tightened.
ATTEMPT_KEYWORDS = (
    "connection rejected",
    "forbidden by access-list",
)


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
        # the event bus on every poll while a device is still pending
        # (or repeatedly retrying and getting rejected).
        self._known_pending: set[str] = set()

        # Devices that were already connected the first time we polled.
        # These are treated as "already there" and never trigger a
        # notification/pending state - only devices that show up AFTER
        # this baseline is captured count as genuinely new. (Only
        # relevant before strict mode / the catch-all rule is enabled.)
        self._baseline: set[str] | None = None

        # Highest RouterOS log ".id" (hex, monotonically increasing)
        # already processed, so we don't reprocess old log lines.
        self._last_log_id: int = -1

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch registration table, access list, and new log entries."""

        registration = await self.api.registration_table()
        access_list = await self.api.get_access_list()

        # DHCP leases + ARP table are only used to extend device_tracker
        # coverage to wired/LAN clients (phones, tablets, laptops) that
        # never touch the WiFi registration-table. They play no role in
        # the approve/reject/strict-mode logic below, which stays
        # WiFi-only on purpose.
        try:
            leases = await self.api.get_leases()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Failed to fetch DHCP leases: %s", err)
            leases = []

        try:
            arp_table = await self.api.get_arp_table()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Failed to fetch ARP table: %s", err)
            arp_table = []

        decided_macs = {
            entry.get("mac-address", "").lower()
            for entry in access_list
            if entry.get("mac-address")
        }

        strict_mode = any(
            entry.get("comment") == CATCHALL_COMMENT for entry in access_list
        )

        seen_macs: set[str] = {
            entry.get("mac-address", "").lower()
            for entry in registration
            if entry.get("mac-address")
        }

        pending: list[dict[str, Any]] = []

        # --- 1. Devices connected but not yet decided ---

        if strict_mode:
            # Once strict mode is on, the access-list is the ONLY source
            # of truth. The pre-strict-mode "baseline" (whatever was
            # connected before strict mode existed) no longer grants a
            # free pass - otherwise a device that happened to be
            # connected during an integration reload would be exempted
            # forever, even after being removed and reconnecting.
            for entry in registration:
                mac = entry.get("mac-address", "")

                if not mac:
                    continue

                mac_lower = mac.lower()

                if mac_lower in decided_macs:
                    continue

                self._notify_pending(
                    pending,
                    mac=mac,
                    interface=entry.get("interface"),
                    ip=entry.get("last-ip"),
                    comment=entry.get("comment", ""),
                )

                # Backstop: on some RouterOS/wifi-qcom firmware, the
                # access-list reject rule doesn't reliably block every
                # connection attempt (a known quirk - the device can
                # slip through on a retry). Actively kick anything
                # that isn't approved, every poll cycle, so it never
                # stays connected for more than ~DEFAULT_SCAN_INTERVAL
                # seconds while undecided.
                try:
                    await self.api.disconnect(mac)
                except Exception:  # noqa: BLE001
                    # Already gone by the time we tried, or a
                    # transient API error - nothing to do here, the
                    # next poll will try again if it's still there.
                    pass
        elif self._baseline is None:
            # First poll ever, strict mode not enabled yet: everything
            # currently connected is considered "already known", not a
            # pending approval. This is purely informational until you
            # run enable_strict_mode.
            self._baseline = set(seen_macs)
        else:
            for entry in registration:
                mac = entry.get("mac-address", "")

                if not mac:
                    continue

                mac_lower = mac.lower()

                if mac_lower in decided_macs or mac_lower in self._baseline:
                    continue

                self._notify_pending(
                    pending,
                    mac=mac,
                    interface=entry.get("interface"),
                    ip=entry.get("last-ip"),
                    comment=entry.get("comment", ""),
                )

        # --- 2. Blocked attempts, detected via the router log ---

        if strict_mode:
            try:
                log_entries = await self.api.get_logs()
                _LOGGER.debug("Fetched %d log entries", len(log_entries))
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Failed to fetch RouterOS logs: %s", err)
                log_entries = []

            seen_in_log: set[str] = set()

            for entry in log_entries:
                message = entry.get("message", "")

                if not any(kw in message.lower() for kw in ATTEMPT_KEYWORDS):
                    continue

                match = MAC_RE.search(message)

                if not match:
                    continue

                mac = match.group(1)
                mac_lower = mac.lower()

                if mac_lower in decided_macs or mac_lower in seen_in_log:
                    continue

                seen_in_log.add(mac_lower)

                self._notify_pending(
                    pending, mac=mac, interface=None, ip=None, comment=""
                )

        # A MAC that has been decided (approved/rejected) no longer
        # needs to be remembered - if it's later removed from the
        # access-list and tries again, it should notify again.
        self._known_pending -= decided_macs

        return {
            "pending": pending,
            "registration": registration,
            "access_list": access_list,
            "strict_mode": strict_mode,
            "leases": leases,
            "arp": arp_table,
        }

    def _notify_pending(
        self,
        pending: list[dict[str, Any]],
        *,
        mac: str,
        interface: str | None,
        ip: str | None,
        comment: str,
    ) -> None:
        """Add a device to the pending list and fire the event once."""

        mac_lower = mac.lower()

        pending.append(
            {
                ATTR_MAC: mac,
                ATTR_INTERFACE: interface,
                ATTR_NAME: comment or interface or mac,
            }
        )

        if mac_lower in self._known_pending:
            return

        self._known_pending.add(mac_lower)

        self.hass.bus.async_fire(
            EVENT_NEW_DEVICE,
            {
                ATTR_MAC: mac,
                ATTR_INTERFACE: interface,
                ATTR_IP: ip,
                ATTR_COMMENT: comment,
            },
        )
