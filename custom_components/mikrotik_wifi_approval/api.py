"""REST API client for MikroTik RouterOS."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import CATCHALL_COMMENT, LOGGING_RULE_COMMENT, LOGGING_TOPICS
from .exceptions import (
    ApiError,
    CannotConnect,
    InvalidAuth,
)


class MikrotikApiClient:
    """MikroTik RouterOS REST API client."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
        use_ssl: bool = False,
    ) -> None:
        """Initialize API client."""

        protocol = "https" if use_ssl else "http"

        self._base_url = f"{protocol}://{host}/rest"

        self._session = session

        self._auth = aiohttp.BasicAuth(
            login=username,
            password=password,
        )

    async def _request(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        """Execute REST request."""

        url = f"{self._base_url}{endpoint}"

        try:
            async with self._session.request(
                method,
                url,
                auth=self._auth,
                json=payload,
            ) as response:

                if response.status == 401:
                    raise InvalidAuth()

                if response.status >= 400:
                    raise ApiError(
                        f"HTTP {response.status}: {await response.text()}"
                    )

                if response.content_type == "application/json":
                    return await response.json()

                return await response.text()

        except aiohttp.ClientError as err:
            raise CannotConnect() from err

    # --------------------------------------------------------
    # System
    # --------------------------------------------------------

    async def identity(self) -> dict[str, Any]:
        """Return router identity."""

        return await self._request(
            "GET",
            "/system/identity",
        )

    # --------------------------------------------------------
    # WiFi Access List
    # --------------------------------------------------------

    async def get_access_list(self) -> list[dict[str, Any]]:
        """Return WiFi access list."""

        return await self._request(
            "GET",
            "/interface/wifi/access-list",
        )

    async def approve(
        self,
        mac: str,
        comment: str = "",
    ) -> dict[str, Any]:
        """Approve WiFi device."""

        result = await self._request(
            "PUT",
            "/interface/wifi/access-list",
            {
                "mac-address": mac,
                "action": "accept",
                "comment": comment,
            },
        )

        await self.bump_catchall()

        return result

    async def reject(
        self,
        mac: str,
        comment: str = "",
    ) -> dict[str, Any]:
        """Reject WiFi device."""

        result = await self._request(
            "PUT",
            "/interface/wifi/access-list",
            {
                "mac-address": mac,
                "action": "reject",
                "comment": comment,
            },
        )

        await self.bump_catchall()

        return result

    async def delete_access(
        self,
        item_id: str,
    ) -> Any:
        """Delete access-list entry."""

        return await self._request(
            "DELETE",
            f"/interface/wifi/access-list/{item_id}",
        )

    # --------------------------------------------------------
    # DHCP
    # --------------------------------------------------------

    async def get_leases(self) -> list[dict[str, Any]]:
        """Return DHCP leases."""

        return await self._request(
            "GET",
            "/ip/dhcp-server/lease",
        )

    async def make_static(
        self,
        lease_id: str,
    ) -> Any:
        """Convert DHCP lease to static."""

        return await self._request(
            "POST",
            f"/ip/dhcp-server/lease/make-static/.id={lease_id}",
        )

    # --------------------------------------------------------
    # Registration Table
    # --------------------------------------------------------

    async def registration_table(self) -> list[dict[str, Any]]:
        """Return WiFi registration table."""

        return await self._request(
            "GET",
            "/interface/wifi/registration-table",
        )

    async def find_registration_by_mac(
        self,
        mac: str,
    ) -> dict[str, Any] | None:
        """Find a registration-table entry by MAC address."""

        entries = await self.registration_table()

        mac_lower = mac.lower()

        for entry in entries:
            if entry.get("mac-address", "").lower() == mac_lower:
                return entry

        return None

    async def find_lease_by_mac(
        self,
        mac: str,
    ) -> dict[str, Any] | None:
        """Find a DHCP lease entry by MAC address."""

        leases = await self.get_leases()

        mac_lower = mac.lower()

        for lease in leases:
            if lease.get("mac-address", "").lower() == mac_lower:
                return lease

        return None

    # --------------------------------------------------------
    # ARP (live L2 presence for LAN/wired clients)
    # --------------------------------------------------------

    async def get_arp_table(self) -> list[dict[str, Any]]:
        """Return the ARP table (any interface, wired or wireless).

        DHCP leases stay 'bound' for the whole lease duration regardless
        of whether the device is actually online right now, so they're
        not reliable for presence detection. The ARP table reflects
        which MACs are currently resolvable on the LAN, which is a much
        better proxy for "is this device home" for wired clients.
        """

        return await self._request(
            "GET",
            "/ip/arp",
        )

    async def disconnect(
        self,
        mac: str,
    ) -> None:
        """Force-disconnect a WiFi client by deleting its registration-table entry."""

        entry = await self.find_registration_by_mac(mac)

        if entry is None:
            raise ApiError(f"No active registration found for {mac}")

        await self._request(
            "DELETE",
            f"/interface/wifi/registration-table/{entry['.id']}",
        )

    # --------------------------------------------------------
    # Strict mode: catch-all reject rule + bulk approve
    # --------------------------------------------------------

    async def _find_catchall(self) -> dict[str, Any] | None:
        """Find the tagged catch-all reject rule, if it exists."""

        entries = await self.get_access_list()

        for entry in entries:
            if entry.get("comment") == CATCHALL_COMMENT:
                return entry

        return None

    async def bump_catchall(self) -> None:
        """Re-create the catch-all reject rule so it stays the LAST rule.

        RouterOS access-list rules are evaluated top to bottom, and newly
        added rules are appended at the end. Whenever we add a new
        accept/reject rule for a specific MAC, the catch-all rule (if it
        exists) must be deleted and re-added so it remains last.

        No-op if strict mode hasn't been enabled yet (no catch-all rule).
        """

        existing = await self._find_catchall()

        if existing is None:
            return

        await self._request(
            "DELETE",
            f"/interface/wifi/access-list/{existing['.id']}",
        )

        await self._create_catchall()

    async def _create_catchall(self) -> None:
        """Create the tagged catch-all reject rule.

        Note: on some RouterOS/wifi-qcom firmware versions (observed on
        AX2/AX3 hardware), an access-list rule with NO matching criteria
        at all is silently ignored by the firmware, even though the
        official docs say an empty rule should match everything. We work
        around this two ways: an explicit always-true signal-range, AND
        the classic MikroTik "match any MAC" wildcard (mac-address
        00:00:00:00:00:00 with an all-zero mask, meaning "ignore every
        bit of the MAC when matching").
        """

        await self._request(
            "PUT",
            "/interface/wifi/access-list",
            {
                "action": "reject",
                "comment": CATCHALL_COMMENT,
                "signal-range": "-120..120",
                "mac-address": "00:00:00:00:00:00",
                "mac-address-mask": "00:00:00:00:00:00",
            },
        )

    async def enable_strict_mode(self) -> None:
        """Approve every currently connected device, then (re)create the
        catch-all reject rule.

        This is the safe order: run this once and every device that is
        already trusted on your network keeps working, while any device
        that connects afterwards (or reconnects after being removed)
        must be explicitly approved. Always recreates the catch-all rule
        (even if one already exists), so re-running this after an update
        picks up any fixes to how that rule is built.
        """

        await self.approve_all_current()

        existing = await self._find_catchall()

        if existing is not None:
            await self._request(
                "DELETE",
                f"/interface/wifi/access-list/{existing['.id']}",
            )

        await self._create_catchall()

    async def approve_all_current(self) -> int:
        """Add an explicit 'accept' rule for every currently connected
        device that doesn't already have one. Returns how many were added.
        """

        registration = await self.registration_table()
        access_list = await self.get_access_list()

        decided_macs = {
            entry.get("mac-address", "").lower()
            for entry in access_list
            if entry.get("mac-address")
        }

        added = 0

        for entry in registration:
            mac = entry.get("mac-address", "")

            if not mac or mac.lower() in decided_macs:
                continue

            await self._request(
                "PUT",
                "/interface/wifi/access-list",
                {
                    "mac-address": mac,
                    "action": "accept",
                    "comment": "auto-approved (already connected)",
                },
            )

            decided_macs.add(mac.lower())
            added += 1

        if added:
            await self.bump_catchall()

        return added

    # --------------------------------------------------------
    # Log reading (to catch attempts that never reach the
    # registration-table because they were rejected outright)
    # --------------------------------------------------------

    async def ensure_logging_rule(self) -> None:
        """Make sure a memory logging rule for wifi/debug exists."""

        rules = await self._request("GET", "/system/logging")

        for rule in rules:
            if rule.get("comment") == LOGGING_RULE_COMMENT:
                return

        await self._request(
            "PUT",
            "/system/logging",
            {
                "topics": LOGGING_TOPICS,
                "action": "memory",
                "comment": LOGGING_RULE_COMMENT,
            },
        )

    async def get_logs(self) -> list[dict[str, Any]]:
        """Return current system log entries."""

        return await self._request("GET", "/log")

    # --------------------------------------------------------
    # Generic
    # --------------------------------------------------------

    async def get(
        self,
        endpoint: str,
    ) -> Any:
        """Generic GET."""

        return await self._request(
            "GET",
            endpoint,
        )

    async def put(
        self,
        endpoint: str,
        payload: dict[str, Any],
    ) -> Any:
        """Generic PUT."""

        return await self._request(
            "PUT",
            endpoint,
            payload,
        )

    async def post(
        self,
        endpoint: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        """Generic POST."""

        return await self._request(
            "POST",
            endpoint,
            payload,
        )

    async def delete(
        self,
        endpoint: str,
    ) -> Any:
        """Generic DELETE."""

        return await self._request(
            "DELETE",
            endpoint,
        )