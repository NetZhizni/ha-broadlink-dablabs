# Broadlink (DAB-LABS async) for Home Assistant

*[Читати українською](README.uk.md)*

An alternative Broadlink integration for Home Assistant, built on
[DAB-LABS/python-broadlink](https://github.com/DAB-LABS/python-broadlink) — the
maintained async fork of `mjg59/python-broadlink` that HA core currently uses
and which has not received changes since 2024.

Integration domain: **`broadlink_dablabs`** — separate from the stock
`broadlink` integration, so both can run side by side without conflicts.

## Why this exists

- `mjg59/python-broadlink` (the stock integration's dependency) has not
  received changes since 2024, so new devices (e.g. RM5 Plus) never make it
  into HA officially.
- DAB-LABS maintains the fork specifically so HA can get fixes and new
  devices, including RM5 Plus (`0x5224`).
- This integration **vendors** the DAB-LABS code directly into
  `custom_components/broadlink_dablabs/blk/` instead of pulling it in as a pip
  package — the DAB-LABS PyPI distribution (`python-broadlink`) installs under
  the same import name `broadlink` as the stock integration's package, so the
  two pip packages would conflict in one venv. Vendoring removes that
  conflict entirely.
- All library calls are genuinely native `asyncio` (UDP transport,
  `asyncio.Lock`, `asyncio.Queue`), so the integration calls them directly via
  `await`, without `hass.async_add_executor_job`.

## What's supported

Platforms: `remote`, `infrared`, `radio_frequency`, `time`, `select`,
`sensor`, `switch`, `light`, `climate` — for the same device families as the
stock integration (RM mini/pro/4/5 Plus, A1/A2, SP1-4, MP1/MP1S, BG1,
LB1/LB2, Hysen thermostats).

**RM5 Plus is supported out of the box**: `INFRARED` + `REMOTE` + `SWITCH` +
`RADIO_FREQUENCY` (experimental, unverified on hardware), with no manual
library patching after every HAOS update.

### Deliberately not ported

- The legacy YAML `switch:` platform (marked deprecated in core itself) — all
  devices are added via Config Flow (UI).
- DHCP auto-discovery — disabled on purpose, to avoid duplicate notifications
  alongside the stock `broadlink` integration. Devices are added manually by
  IP.

### Known limitations

The `infrared` and `radio_frequency` platforms depend on relatively new HA
core base domains (`homeassistant.components.infrared` /
`homeassistant.components.radio_frequency`, the `infrared-protocols` /
`rf-protocols` packages). If your HA version doesn't have them yet, only
these two platforms will fail in the log — the rest (`remote`, `switch`,
`sensor`, `light`, `climate`, `select`, `time`) will work normally.

Requires Python 3.13+ in the HA container (uses default generic parameter
syntax, PEP 696) — this is already a requirement of Home Assistant core
itself in current releases.

## Installation via HACS (Custom repository)

1. HACS → three-dot menu in the top right → **Custom repositories**.
2. URL: `https://github.com/NetZhizni/ha-broadlink-dablabs`, category:
   **Integration**.
3. Find "Broadlink (DAB-LABS async)" in HACS → Download.
4. Restart Home Assistant.
5. Settings → Devices & Services → Add Integration → **Broadlink (DAB-LABS
   async)** → enter the device's IP address (e.g. RM5 Plus).

## Manual installation (without HACS)

Copy `custom_components/broadlink_dablabs/` into
`config/custom_components/` of your HA instance and restart Home Assistant.

## Icon

The integration ships its own icon/logo
(`custom_components/broadlink_dablabs/brand/`), identical to the ones used by
the stock `broadlink` integration in
[home-assistant/brands](https://github.com/home-assistant/brands). Starting
with Home Assistant 2026.3+, custom integrations can ship brand images
directly in their own folder (`brand/icon.png`, `brand/logo.png`, etc.) — a
separate request to the brands repository is no longer needed, and the icon
appears in the UI right after installation.

## License

MIT, see [LICENSE](LICENSE). The code in
`custom_components/broadlink_dablabs/blk/` is vendored from
[DAB-LABS/python-broadlink](https://github.com/DAB-LABS/python-broadlink)
under its own MIT license — see
[blk/LICENSE](custom_components/broadlink_dablabs/blk/LICENSE).
