"""Best-effort vendor (manufacturer) lookup from a MAC address' OUI.

Rather than bundling a static copy of the IEEE OUI registry (30k+
entries, several MB, and stale the day after it's embedded), this
calls the free api.macvendors.com lookup service and caches results
in memory for the lifetime of the HA process. A lookup failure (rate
limit, network error, unknown OUI) is never fatal - it just means no
vendor name gets shown, same as if this feature didn't exist.
"""

from __future__ import annotations

import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

# Cached by OUI prefix ("AA:BB:CC"), not full MAC, since the vendor is
# the same for every device sharing that prefix. Value is None for
# "looked up, no vendor found" so we don't repeat a failed lookup.
_CACHE: dict[str, str | None] = {}


def is_randomized_mac(mac: str) -> bool:
    """Return True if the MAC has the 'locally administered' bit set.

    This is the standard signature of a privacy/random WiFi MAC (iOS,
    modern Android). The real hardware OUI is deliberately hidden in
    this case, so a vendor lookup would be meaningless (or actively
    misleading) - always skip it.
    """

    try:
        first_octet = int(mac.split(":")[0], 16)
    except (ValueError, IndexError):
        return False

    return bool(first_octet & 0x02)


async def lookup_vendor(
    session: aiohttp.ClientSession,
    mac: str,
) -> str | None:
    """Look up the manufacturer for a MAC address. Returns None on any
    failure or if the MAC is a randomized/private address.
    """

    if not mac or is_randomized_mac(mac):
        return None

    prefix = mac.upper()[:8]  # "AA:BB:CC"

    if prefix in _CACHE:
        return _CACHE[prefix]

    try:
        async with session.get(
            f"https://api.macvendors.com/{mac}",
            timeout=aiohttp.ClientTimeout(total=3),
        ) as resp:
            if resp.status == 200:
                vendor = (await resp.text()).strip()
                _CACHE[prefix] = vendor or None
                return _CACHE[prefix]

            # 404 = OUI not in their database, 429 = rate limited.
            # Either way: remember "no answer" so we don't ask again
            # for this prefix every single poll cycle.
            _CACHE[prefix] = None
            return None
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Vendor lookup failed for %s: %s", mac, err)
        return None
