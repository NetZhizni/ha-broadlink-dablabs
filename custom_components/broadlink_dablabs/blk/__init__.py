"""Vendored async Broadlink client, trimmed to the device families this integration wires up.

Source: DAB-LABS/python-broadlink (MIT license), vendored as private source
instead of a pip dependency. Its PyPI distribution ("python-broadlink")
installs into the same top-level "broadlink" import name as the
mjg59/python-broadlink package the core "broadlink" integration depends on --
two pip packages cannot safely coexist under one import name in the same
Home Assistant virtualenv, so this integration bundles the source directly
and never touches site-packages/broadlink.
"""

import contextlib
from collections.abc import AsyncGenerator

from . import exceptions as e
from .climate import hysen
from .const import DEFAULT_BCAST_ADDR, DEFAULT_PORT, DEFAULT_TIMEOUT
from .device import Device, ping, scan, send_setup_packet
from .light import lb1, lb2
from .remote import rm, rm4, rm4mini, rm4pro, rm5plus, rmmini, rmminib, rmpro
from .sensor import a1, a2
from .switch import bg1, mp1, mp1s, sp1, sp2, sp2s, sp3, sp3s, sp4, sp4b

SUPPORTED_TYPES = {
    sp1: {
        0x0000: ("SP1", "Broadlink"),
    },
    sp2: {
        0x2717: ("NEO", "Ankuoo"),
        0x2719: ("SP2-compatible", "Honeywell"),
        0x271A: ("SP2-compatible", "Honeywell"),
        0x2720: ("SP mini", "Broadlink"),
        0x2728: ("SP2-compatible", "URANT"),
        0x273E: ("SP mini", "Broadlink"),
        0x7530: ("SP2", "Broadlink (OEM)"),
        0x7539: ("SP2-IL", "Broadlink (OEM)"),
        0x753E: ("SP mini 3", "Broadlink"),
        0x7540: ("MP2", "Broadlink"),
        0x7544: ("SP2-CL", "Broadlink"),
        0x7546: ("SP2-UK/BR/IN", "Broadlink (OEM)"),
        0x7547: ("SC1", "Broadlink"),
        0x7549: ("SP mini 3", "Broadlink (OEM)"),
        0x7918: ("SP2", "Broadlink (OEM)"),
        0x7919: ("SP2-compatible", "Honeywell"),
        0x791A: ("SP2-compatible", "Honeywell"),
        0x7D0D: ("SP mini 3", "Broadlink (OEM)"),
    },
    sp2s: {
        0x2711: ("SP2", "Broadlink"),
        0x2716: ("NEO PRO", "Ankuoo"),
        0x271D: ("Ego", "Efergy"),
        0x2736: ("SP mini+", "Broadlink"),
    },
    sp3: {
        0x2733: ("SP3", "Broadlink"),
        0x7D00: ("SP3-EU", "Broadlink (OEM)"),
    },
    sp3s: {
        0x9479: ("SP3S-US", "Broadlink"),
        0x947A: ("SP3S-EU", "Broadlink"),
    },
    sp4: {
        0x7568: ("SP4L-CN", "Broadlink"),
        0x756B: ("SP4M-JP", "Broadlink"),
        0x756C: ("SP4M", "Broadlink"),
        0x756F: ("MCB1", "Broadlink"),
        0x7579: ("SP4L-EU", "Broadlink"),
        0x757B: ("SP4L-AU", "Broadlink"),
        0x7583: ("SP mini 3", "Broadlink"),
        0x7587: ("SP4L-UK", "Broadlink"),
        0x7D11: ("SP mini 3", "Broadlink"),
        0x7D15: ("SP mini 3-AL", "Broadlink (OEM)"),
        0xA4F9: ("WS4", "Broadlink (OEM)"),
        0xA569: ("SP4L-UK", "Broadlink"),
        0xA56A: ("MCB1", "Broadlink"),
        0xA56B: ("SCB1E", "Broadlink"),
        0xA56C: ("SP4L-EU", "Broadlink"),
        0xA576: ("SP4L-AU", "Broadlink"),
        0xA589: ("SP4L-UK", "Broadlink"),
        0xA5D3: ("SP4L-EU", "Broadlink"),
        0xA57A: ("SP4", "Broadlink"),
        0xA6F4: ("SP4D-US", "Broadlink"),
    },
    sp4b: {
        0x5115: ("SCB1E", "Broadlink"),
        0x51E2: ("AHC/U-01", "BG Electrical"),
        0x6111: ("MCB1", "Broadlink"),
        0x6113: ("SCB1E", "Broadlink"),
        0x618B: ("SP4L-EU", "Broadlink"),
        0x6489: ("SP4L-AU", "Broadlink"),
        0x648B: ("SP4M-US", "Broadlink"),
        0x648C: ("SP4L-US", "Broadlink"),
        0x6494: ("SCB2", "Broadlink"),
    },
    rmmini: {
        0x2737: ("RM mini 3", "Broadlink"),
        0x278F: ("RM mini", "Broadlink"),
        0x27B7: ("RM mini 3", "Broadlink"),
        0x27C2: ("RM mini 3", "Broadlink"),
        0x27C7: ("RM mini 3", "Broadlink"),
        0x27C8: ("RM mini 3", "Broadlink"),
        0x27CC: ("RM mini 3", "Broadlink"),
        0x27CD: ("RM mini 3", "Broadlink"),
        0x27D0: ("RM mini 3", "Broadlink"),
        0x27D1: ("RM mini 3", "Broadlink"),
        0x27D3: ("RM mini 3", "Broadlink"),
        0x27DC: ("RM mini 3", "Broadlink"),
        0x27DE: ("RM mini 3", "Broadlink"),
        0xA544: ("RM mini 3", "Broadlink (OEM)"),
    },
    rmpro: {
        0x2712: ("RM pro/pro+", "Broadlink"),
        0x272A: ("RM pro", "Broadlink"),
        0x273D: ("RM pro", "Broadlink"),
        0x277C: ("RM home", "Broadlink"),
        0x2783: ("RM home", "Broadlink"),
        0x2787: ("RM pro", "Broadlink"),
        0x278B: ("RM plus", "Broadlink"),
        0x2797: ("RM pro+", "Broadlink"),
        0x279D: ("RM pro+", "Broadlink"),
        0x27A1: ("RM plus", "Broadlink"),
        0x27A6: ("RM plus", "Broadlink"),
        0x27A9: ("RM pro+", "Broadlink"),
        0x27C3: ("RM pro+", "Broadlink"),
        0xAF8B: ("RM Max", "Broadlink"),
    },
    rmminib: {
        0x5F36: ("RM mini 3", "Broadlink"),
        0x6507: ("RM mini 3", "Broadlink"),
        0x6508: ("RM mini 3", "Broadlink"),
    },
    rm4mini: {
        0x51DA: ("RM4 mini", "Broadlink"),
        0x5209: ("RM4 TV mate", "Broadlink"),
        0x520C: ("RM4 mini", "Broadlink"),
        0x520D: ("RM4C mini", "Broadlink"),
        0x5211: ("RM4C mate", "Broadlink"),
        0x5212: ("RM4 TV mate", "Broadlink"),
        0x5216: ("RM4 mini", "Broadlink"),
        0x521C: ("RM4 mini", "Broadlink"),
        0x6070: ("RM4C mini", "Broadlink"),
        0x610E: ("RM4 mini", "Broadlink"),
        0x610F: ("RM4C mini", "Broadlink"),
        0x62BC: ("RM4 mini", "Broadlink"),
        0x62BE: ("RM4C mini", "Broadlink"),
        0x6364: ("RM4S", "Broadlink"),
        0x648D: ("RM4 mini", "Broadlink"),
        0x6539: ("RM4C mini", "Broadlink"),
        0x653A: ("RM4 mini", "Broadlink"),
    },
    rm4pro: {
        0x520B: ("RM4 pro", "Broadlink"),
        0x5213: ("RM4 pro", "Broadlink"),
        0x5218: ("RM4C pro", "Broadlink"),
        0x6026: ("RM4 pro", "Broadlink"),
        0x6184: ("RM4C pro", "Broadlink"),
        0x61A2: ("RM4 pro", "Broadlink"),
        0x649B: ("RM4 pro", "Broadlink"),
        0x653C: ("RM4 pro", "Broadlink"),
    },
    rm5plus: {
        0x5224: ("RM5 plus", "Broadlink"),
    },
    a1: {
        0x2714: ("A1", "Broadlink"),
    },
    a2: {
        0x4F60: ("A2", "Broadlink"),
    },
    mp1: {
        0x4EB5: ("MP1-1K4S", "Broadlink"),
        0x4EDA: ("MP1-1K3S2U", "Broadlink"),
        0x4F1B: ("MP1-1K3S2U", "Broadlink (OEM)"),
        0x4F65: ("MP1-1K3S2U", "Broadlink"),
    },
    mp1s: {
        0x4EF7: ("MP1-1K4S", "Broadlink (OEM)"),
    },
    lb1: {
        0x5043: ("SB800TD", "Broadlink (OEM)"),
        0x504E: ("LB1", "Broadlink"),
        0x606D: ("SLA22RGB9W81/SLA27RGB9W81", "Luceco"),
        0x606E: ("SB500TD", "Broadlink (OEM)"),
        0x60C7: ("LB1", "Broadlink"),
        0x60C8: ("LB1", "Broadlink"),
        0x6112: ("LB1", "Broadlink"),
        0x644B: ("LB1", "Broadlink"),
        0x644C: ("LB27 R1", "Broadlink"),
        0x644E: ("LB26 R1", "Broadlink"),
        0x6488: ("LB27 C1", "Broadlink"),
        0x6498: ("SMART+ WIFI CEILING TW 24W", "LEDVANCE"),
    },
    lb2: {
        0xA4F4: ("LB27 R1", "Broadlink"),
        0xA5F7: ("LB27 R1", "Broadlink"),
        0xA6EF: ("EFCF60WSMT", "Luceco"),
        0xA517: ("LB26 R1", "Broadlink"),
    },
    hysen: {
        0x4EAD: ("HY02/HY03", "Hysen"),
    },
    bg1: {
        0x51E3: ("BG800/BG900", "BG Electrical"),
    },
}


def gendevice(
    dev_type: int,
    host: tuple[str, int],
    mac: bytes | str,
    name: str = "",
    is_locked: bool = False,
) -> Device:
    """Generate a device."""
    for dev_cls, products in SUPPORTED_TYPES.items():
        try:
            model, manufacturer = products[dev_type]

        except KeyError:
            continue

        return dev_cls(
            host,
            mac,
            dev_type,
            name=name,
            model=model,
            manufacturer=manufacturer,
            is_locked=is_locked,
        )

    return Device(host, mac, dev_type, name=name, is_locked=is_locked)


async def hello(
    ip_address: str,
    port: int = DEFAULT_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> Device:
    """Direct device discovery. Useful if the device is locked."""
    async with contextlib.aclosing(
        xdiscover(
            timeout=timeout,
            discover_ip_address=ip_address,
            discover_ip_port=port,
        )
    ) as devices:
        async for device in devices:
            return device
    raise e.NetworkTimeoutError(
        -4000,
        "Network timeout",
        f"No response received within {timeout}s",
    )


async def discover(
    timeout: float = DEFAULT_TIMEOUT,
    local_ip_address: str | None = None,
    discover_ip_address: str = DEFAULT_BCAST_ADDR,
    discover_ip_port: int = DEFAULT_PORT,
) -> list[Device]:
    """Discover devices connected to the local network."""
    devices = xdiscover(timeout, local_ip_address, discover_ip_address, discover_ip_port)
    async with contextlib.aclosing(devices):
        return [device async for device in devices]


async def xdiscover(
    timeout: float = DEFAULT_TIMEOUT,
    local_ip_address: str | None = None,
    discover_ip_address: str = DEFAULT_BCAST_ADDR,
    discover_ip_port: int = DEFAULT_PORT,
) -> AsyncGenerator[Device]:
    """Discover devices connected to the local network, yielding each as it answers."""
    responses = scan(timeout, local_ip_address, discover_ip_address, discover_ip_port)
    async with contextlib.aclosing(responses):
        async for resp in responses:
            yield gendevice(*resp)
