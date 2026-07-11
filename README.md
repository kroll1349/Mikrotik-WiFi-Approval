# MikroTik WiFi Approval

A Home Assistant custom integration that lets you **approve or reject new WiFi devices from a push notification**, backed by a MikroTik router — similar to the "guest approval" feature on some consumer mesh routers, but for MikroTik + Home Assistant.

> ⚠️ **Status: works reliably on the author's own hardware, not yet broadly tested.** See [Compatibility](#compatibility) and [Known limitations](#known-limitations) before installing. This is shared as-is for anyone who wants to experiment or contribute — it is not a polished, universally-supported product.

## What it does

- Detects when an unrecognized device connects (or tries to connect) to your WiFi.
- Sends a push notification (via the Home Assistant Companion app) with **Approve** / **Reject** buttons.
- Approving adds the device to the router's access list and lets it connect.
- Rejecting blocks it — and keeps blocking it, even on retry.
- Optional "strict mode": unapproved devices are refused at the WiFi authentication level (not just informational).

## Compatibility

**Tested on:**
- RouterOS 7.23.2
- MikroTik hAP ax2 (CAPsMAN, `/interface/wifi` — the new "wifi-qcom" menu) as the controller
- MikroTik hAP ac2 as a CAPsMAN-provisioned CAP

**Not tested / likely broken on:**
- The legacy `/interface/wireless` menu (older RouterOS 6.x style, or wifi-qcom-ac2 devices not migrated to the new package). This integration talks exclusively to `/interface/wifi/*` REST endpoints.
- Other RouterOS versions — log message wording for rejected connections (see below) may differ and silently break detection.
- Non-CAPsMAN single-AP setups are untested (should mostly work, since CAPsMAN just adds interfaces named `cap-wifiN` to the same tables — but not verified).

If you try it on different hardware/firmware, please open an issue with what worked and what didn't.

## Known limitations

These are real firmware quirks discovered by trial and error, not implementation choices:

1. **Empty access-list rules are silently ignored.** On this router's firmware, an access-list rule with no matching criteria at all (the documented way to build a "reject everyone else" catch-all) is never evaluated. The workaround adds an explicit `signal-range=-120..120` (matches any real signal) plus the classic `mac-address=00:00:00:00:00:00` / `mac-address-mask=00:00:00:00:00:00` wildcard. This may or may not be needed on other firmware versions — it's a defensive default that shouldn't hurt if it isn't.
2. **CAPsMAN doesn't provision by default.** A CAP's WiFi interfaces default to `configuration.manager=local` even when the CAP successfully discovers and connects to CAPsMAN. If you have a multi-AP CAPsMAN setup, you need to explicitly run, **on each CAP**:
   ```
   /interface/wifi set wifi1,wifi2 configuration.manager=capsman-or-local
   ```
   Otherwise the CAP keeps running its own local config, and the access-list rules you manage from the integration never apply to clients connected through it.
3. **Detection of blocked connection attempts relies on log text matching.** A device rejected at the access-list level never appears in `registration-table` — the only trace is a log line like `connection rejected, forbidden by access-list`. The integration polls `/rest/log`, filters on that exact substring, and extracts the MAC with a regex. If your firmware logs a different message, detection silently does nothing (no error, just no notifications) until the wording is adjusted in `coordinator.py`.
4. **Active-kick backstop.** Because of the two issues above (and because MikroTik's own enforcement wasn't 100% reliable across CAP handoffs during testing), the integration also actively force-disconnects any unapproved device it finds already connected, on every ~5 second poll. This means a device that manages to slip past the access-list will only stay connected for a few seconds before being kicked, rather than being blocked instantly and permanently — treat this as a backstop, not a hard guarantee.
5. **No automated tests, no config-flow validation of RouterOS version/package.** Setup errors currently surface as generic Home Assistant "unknown error" messages rather than clear diagnostics.

## Requirements

- A MikroTik router running RouterOS 7.x with the `/interface/wifi` (wifi-qcom) package.
- RouterOS REST API enabled (`/ip/service enable www` or `www-ssl`), reachable from Home Assistant.
- A RouterOS user with API/REST permissions (`read`, `write`, `api`, `rest-api` policies at minimum).
- Home Assistant with HACS installed, for the integration.
- Home Assistant Companion app on at least one phone, for push notifications.

## Installation

### Integration (via HACS)

1. In HACS, go to **Custom repositories**, add this repo's URL with category **Integration**.
2. Install "MikroTik WiFi Approval" from HACS.
3. Restart Home Assistant.
4. Settings → Devices & services → Add integration → search "MikroTik WiFi Approval" → enter your router's IP, username, password.

### Blueprint (manual import — not installed by HACS)

HACS installs the integration code only; the notification blueprint is a separate GitHub-native mechanism. Click:

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fkroll1349%2FMikrotik-WiFi-Approval%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fkroll1349%2Fmikrotik_wifi_approval.yaml)

Then create an automation from it, pick which phone(s) get notified, and optionally list known device MACs so recognized phones show a name instead of just a MAC address.

## Enabling real blocking (strict mode)

By default, after setup, the integration only *observes* — it won't block anything until you explicitly turn on enforcement. This order matters, so it won't lock out your own devices:

```yaml
service: mikrotik_wifi_approval.enable_strict_mode
```

This approves everything currently connected, then adds the catch-all reject rule. From that point on, any new/unrecognized device is refused until approved from a notification.

## Services

| Service | Description |
|---|---|
| `mikrotik_wifi_approval.approve` | Add a MAC to the access list with `action=accept`. |
| `mikrotik_wifi_approval.reject` | Add a MAC to the access list with `action=reject`. |
| `mikrotik_wifi_approval.disconnect` | Force-disconnect an already-connected client. |
| `mikrotik_wifi_approval.make_static` | Convert a device's DHCP lease to static. |
| `mikrotik_wifi_approval.approve_all_current` | Bulk-approve everything currently connected. |
| `mikrotik_wifi_approval.enable_strict_mode` | Bulk-approve + enable the catch-all reject rule. |

## Troubleshooting

- **No notification ever arrives, but the "Pending devices" sensor updates correctly:** reload the integration (not a full HA restart) so the coordinator re-evaluates currently-blocked devices with automations already listening.
- **Rejected device reconnects successfully anyway:** check whether it was auto-approved by a previous `enable_strict_mode` run (it bulk-approves whatever's connected at that moment) — check the access-list entry's comment.
- **Notification never fires despite log lines showing rejections:** confirm the log message wording matches `ATTEMPT_KEYWORDS` in `coordinator.py`; adjust if your firmware phrases it differently.

## Should you use this?

If you're comfortable reading RouterOS logs, editing Python, and debugging firmware quirks yourself — yes, feel free. If you want a polished, plug-and-play solution that works on any MikroTik out of the box, this isn't there yet. Issues and PRs (especially compatibility reports from other hardware/firmware) are welcome.

## License

Copyright (c) 2026 kroll

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
