"""The MikroTik WiFi Approval integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MikrotikApiClient
from .const import (
    ATTR_COMMENT,
    ATTR_MAC,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    DOMAIN,
    SERVICE_APPROVE,
    SERVICE_DISCONNECT,
    SERVICE_MAKE_STATIC,
    SERVICE_REJECT,
)
from .coordinator import MikrotikWifiCoordinator
from .exceptions import ApiError

PLATFORMS: list[Platform] = [Platform.SENSOR]

SERVICE_MAC_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MAC): str,
        vol.Optional(ATTR_COMMENT, default=""): str,
    }
)

SERVICE_MAC_ONLY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MAC): str,
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration from YAML."""
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Set up a config entry."""

    session = async_get_clientsession(hass)

    api = MikrotikApiClient(
        host=entry.data[CONF_HOST],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        session=session,
    )

    coordinator = MikrotikWifiCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(
        entry,
        PLATFORMS,
    )

    _async_register_services(hass)

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


def _get_first_api(hass: HomeAssistant) -> MikrotikApiClient:
    """Return the API client of the first configured entry.

    Most setups only have one router. If multiple entries exist,
    services act on the first one unless extended to target a specific
    device.
    """

    coordinators = list(hass.data.get(DOMAIN, {}).values())

    if not coordinators:
        raise ApiError("No MikroTik WiFi Approval config entry is set up")

    return coordinators[0].api


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the approve/reject/disconnect/make_static services."""

    if hass.services.has_service(DOMAIN, SERVICE_APPROVE):
        return

    async def handle_approve(call: ServiceCall) -> None:
        api = _get_first_api(hass)
        await api.approve(call.data[ATTR_MAC], call.data.get(ATTR_COMMENT, ""))

    async def handle_reject(call: ServiceCall) -> None:
        api = _get_first_api(hass)
        await api.reject(call.data[ATTR_MAC], call.data.get(ATTR_COMMENT, ""))

    async def handle_disconnect(call: ServiceCall) -> None:
        api = _get_first_api(hass)
        await api.disconnect(call.data[ATTR_MAC])

    async def handle_make_static(call: ServiceCall) -> None:
        api = _get_first_api(hass)
        lease = await api.find_lease_by_mac(call.data[ATTR_MAC])

        if lease is None:
            raise ApiError(f"No DHCP lease found for {call.data[ATTR_MAC]}")

        await api.make_static(lease[".id"])

    hass.services.async_register(
        DOMAIN, SERVICE_APPROVE, handle_approve, schema=SERVICE_MAC_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_REJECT, handle_reject, schema=SERVICE_MAC_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DISCONNECT,
        handle_disconnect,
        schema=SERVICE_MAC_ONLY_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_MAKE_STATIC,
        handle_make_static,
        schema=SERVICE_MAC_ONLY_SCHEMA,
    )
