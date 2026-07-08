"""REST API client for MikroTik RouterOS."""

from __future__ import annotations

from typing import Any

import aiohttp

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

        return await self._request(
            "PUT",
            "/interface/wifi/access-list",
            {
                "mac-address": mac,
                "action": "accept",
                "comment": comment,
            },
        )

    async def reject(
        self,
        mac: str,
        comment: str = "",
    ) -> dict[str, Any]:
        """Reject WiFi device."""

        return await self._request(
            "PUT",
            "/interface/wifi/access-list",
            {
                "mac-address": mac,
                "action": "reject",
                "comment": comment,
            },
        )

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