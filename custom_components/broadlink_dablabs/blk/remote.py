"""Support for universal remotes."""

import asyncio
import contextlib
import enum
import logging
import struct
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Self

from . import exceptions as e
from .device import Device

_LOGGER = logging.getLogger(__name__)

TICK = 8192 / 269
"""Duration of one Broadlink timing unit in microseconds (about 30.45 us)."""

DEFAULT_POLL_INTERVAL = 0.5
"""Seconds between ``check_data`` polls while a capture window is open."""

DEFAULT_REARM_INTERVAL = 15.0
"""Seconds after which an open capture window re-enters learning mode."""


class SignalKind(enum.IntEnum):
    """The kind of signal a packet carries."""

    IR = 0x26
    RF_433 = 0xB2
    RF_315 = 0xD7

    @property
    def is_rf(self) -> bool:
        """True for the radio bands."""
        return self is not SignalKind.IR

    @classmethod
    def classify(cls, type_byte: int) -> Self:
        """Map a packet's raw first byte to a kind, tolerantly."""
        if type_byte == cls.IR:
            return cls.IR
        if type_byte & 0xF0 == 0xB0:
            return cls.RF_433
        if type_byte & 0xF0 == 0xD0:
            return cls.RF_315
        raise ValueError(f"Unknown packet type 0x{type_byte:02x}")


def pulses_to_data(
    pulses: list[int],
    tick: float = TICK,
    *,
    kind: SignalKind = SignalKind.IR,
    repeat: int = 0,
) -> bytes:
    """Convert a microsecond duration sequence into a Broadlink packet."""
    if not 0 <= repeat <= 0xFF:
        raise ValueError("repeat must be between 0 and 255")
    result = bytearray(4)
    result[0x00] = SignalKind(kind)
    result[0x01] = repeat

    for pulse in pulses:
        div, mod = divmod(round(pulse / tick), 256)
        if div:
            result.append(0)
            result.append(div)
        result.append(mod)

    data_len = len(result) - 4
    result[0x02] = data_len & 0xFF
    result[0x03] = data_len >> 8

    return bytes(result)


def data_to_pulses(data: bytes, tick: float = TICK) -> list[int]:
    """Parse a Broadlink packet into a microsecond duration sequence."""
    result = []
    index = 4
    end = min(256 * data[0x03] + data[0x02] + 4, len(data))

    while index < end:
        chunk = data[index]
        index += 1

        if chunk == 0:
            try:
                chunk = 256 * data[index] + data[index + 1]
            except IndexError as err:
                raise ValueError("Malformed data.") from err
            index += 2

        result.append(int(chunk * tick))

    return result


@dataclass(frozen=True)
class ParsedPacket:
    """The parts of a Broadlink packet: kind, repeat count and timings."""

    kind: SignalKind
    repeat: int
    pulses: tuple[int, ...]
    type_byte: int


def parse_packet(data: bytes, tick: float = TICK) -> ParsedPacket:
    """Split a Broadlink packet into its kind, repeat count and timings."""
    if len(data) < 4:
        raise ValueError("Malformed data.")
    kind = SignalKind.classify(data[0x00])
    return ParsedPacket(kind, data[0x01], tuple(data_to_pulses(data, tick)), data[0x00])


@dataclass(frozen=True)
class CapturedSignal:
    """One signal captured by a universal remote."""

    packet: bytes
    kind: SignalKind
    pulses: tuple[int, ...] = field(repr=False)
    repeat: int = 0
    frequency_mhz: float | None = None
    type_byte: int | None = None
    captured_at: float = field(default_factory=time.time, repr=False, compare=False)

    @classmethod
    def from_packet(
        cls,
        packet: bytes,
        frequency_mhz: float | None = None,
        *,
        kind: SignalKind | None = None,
    ) -> Self:
        """Build a signal from a device-returned packet."""
        if len(packet) < 4:
            raise ValueError("Malformed data.")
        type_byte = packet[0x00]
        if kind is None:
            kind = SignalKind.classify(type_byte)
        return cls(
            bytes(packet),
            kind,
            tuple(data_to_pulses(packet)),
            packet[0x01],
            frequency_mhz,
            type_byte,
        )


class rmmini(Device):
    """Controls a Broadlink RM mini 3."""

    TYPE = "RMMINI"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tx_generation = 0
        self._capturing = False

    @property
    def capture_active(self) -> bool:
        """True while a capture window is open on this device."""
        return self._capturing

    async def _claim_window(self) -> None:
        """Take the receiver for a new window, or refuse."""
        if self._capturing:
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            if self._capturing:
                raise e.CaptureInProgressError(
                    "A capture window is already open; close it with aclose() first"
                )
        self._capturing = True

    def _release_window(self) -> None:
        self._capturing = False

    async def _send(self, command: int, data: bytes = b"") -> bytes:
        """Send a packet to the device."""
        packet = struct.pack("<I", command) + data
        resp = await self.send_packet(0x6A, packet)
        e.check_error(resp[0x22:0x24])
        payload = self.decrypt(resp[0x38:])
        return payload[0x4:]

    async def update(self) -> None:
        """Update device name and lock status."""
        resp = await self._send(0x1)
        self.name = resp[0x48:].split(b"\x00")[0].decode()
        self.is_locked = bool(resp[0x87])

    async def send_data(self, data: bytes) -> None:
        """Send a code to the device."""
        self._tx_generation += 1
        await self._send(0x2, data)

    async def enter_learning(self) -> None:
        """Enter infrared learning mode."""
        await self._send(0x3)

    async def check_data(self) -> bytes:
        """Return the last captured code."""
        return await self._send(0x4)

    def capture(
        self,
        window: float = 30.0,
        *,
        stop_after_first: bool = True,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        rearm_interval: float = DEFAULT_REARM_INTERVAL,
    ) -> AsyncGenerator[CapturedSignal]:
        """Open an infrared capture window and yield what the device hears."""
        return self._capture_loop(
            self.enter_learning,
            window,
            stop_after_first,
            poll_interval,
            rearm_interval,
            SignalKind.IR,
            None,
            claim=True,
        )

    async def _capture_loop(
        self,
        arm: Callable[[], Awaitable[None]],
        window: float,
        stop_after_first: bool,
        poll_interval: float,
        rearm_interval: float,
        kind: SignalKind,
        frequency_mhz: float | None,
        *,
        claim: bool,
    ) -> AsyncGenerator[CapturedSignal]:
        if window < 0:
            raise ValueError("window must be 0 (open-ended) or positive")
        if poll_interval <= 0 or rearm_interval <= 0:
            raise ValueError("poll_interval and rearm_interval must be positive")
        if claim:
            await self._claim_window()
        try:
            body = self._capture_body(
                arm,
                window,
                stop_after_first,
                poll_interval,
                rearm_interval,
                kind,
                frequency_mhz,
            )
            async with contextlib.aclosing(body):
                async for signal in body:
                    yield signal
        finally:
            if claim:
                self._release_window()

    async def _capture_body(
        self,
        arm: Callable[[], Awaitable[None]],
        window: float,
        stop_after_first: bool,
        poll_interval: float,
        rearm_interval: float,
        kind: SignalKind,
        frequency_mhz: float | None,
    ) -> AsyncGenerator[CapturedSignal]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + window if window else None
        timeouts = 0

        await arm()
        armed_at = loop.time()
        generation = self._tx_generation
        _LOGGER.debug("%s: capture window armed (%s)", self.host[0], kind.name)

        while True:
            now = loop.time()
            if deadline is not None and now >= deadline:
                return
            delay = poll_interval
            if deadline is not None:
                delay = min(delay, deadline - now)
            await asyncio.sleep(delay)

            try:
                data = await self.check_data()
            except (e.StorageError, e.ReadError):
                data = b""
            except e.NetworkTimeoutError:
                timeouts += 1
                if timeouts >= 3:
                    raise
                generation = -1  # Re-arm; the device's state is unknown.
                continue
            timeouts = 0

            if data:
                try:
                    signal = CapturedSignal.from_packet(data, frequency_mhz, kind=kind)
                except ValueError as err:
                    _LOGGER.debug(
                        "%s: ignoring an undecodable capture (%s): %s",
                        self.host[0],
                        err,
                        data.hex(),
                    )
                    generation = -1
                else:
                    _LOGGER.debug(
                        "%s: captured %d bytes (%s)", self.host[0], len(data), kind.name
                    )
                    yield signal
                    if stop_after_first:
                        return
                    generation = -1  # One code per session: re-arm.

            now = loop.time()
            if generation != self._tx_generation or now - armed_at >= rearm_interval:
                await arm()
                armed_at = loop.time()
                generation = self._tx_generation
                _LOGGER.debug("%s: capture window re-armed", self.host[0])


class rmpro(rmmini):
    """Controls a Broadlink RM pro."""

    TYPE = "RMPRO"

    async def sweep_frequency(self) -> None:
        """Sweep frequency."""
        await self._send(0x19)

    async def check_frequency(self) -> tuple[bool, float]:
        """Return True if the frequency was identified successfully."""
        resp = await self._send(0x1A)
        is_found = bool(resp[0])
        frequency = struct.unpack("<I", resp[1:5])[0] / 1000.0
        return is_found, frequency

    async def find_rf_packet(self, frequency: float | None = None) -> None:
        """Enter radiofrequency learning mode."""
        payload = bytearray()
        if frequency:
            payload += struct.pack("<I", int(frequency * 1000))
        await self._send(0x1B, payload)

    async def cancel_sweep_frequency(self) -> None:
        """Cancel sweep frequency."""
        await self._send(0x1E)

    def capture_rf(
        self,
        window: float = 30.0,
        *,
        frequency: float | None = None,
        stop_after_first: bool = True,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        rearm_interval: float = DEFAULT_REARM_INTERVAL,
    ) -> AsyncGenerator[CapturedSignal]:
        """Open a radio frequency capture window and yield what the device hears."""
        return self._capture_rf_loop(
            window, frequency, stop_after_first, poll_interval, rearm_interval
        )

    async def _capture_rf_loop(
        self,
        window: float,
        frequency: float | None,
        stop_after_first: bool,
        poll_interval: float,
        rearm_interval: float,
    ) -> AsyncGenerator[CapturedSignal]:
        if window < 0 or poll_interval <= 0:
            raise ValueError("window must be 0 or positive, poll_interval positive")
        await self._claim_window()
        try:
            body = self._capture_rf_body(
                window, frequency, stop_after_first, poll_interval, rearm_interval
            )
            async with contextlib.aclosing(body):
                async for signal in body:
                    yield signal
        finally:
            self._release_window()

    async def _capture_rf_body(
        self,
        window: float,
        frequency: float | None,
        stop_after_first: bool,
        poll_interval: float,
        rearm_interval: float,
    ) -> AsyncGenerator[CapturedSignal]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + window if window else None

        if frequency is None:
            frequency = await self._sweep(deadline, poll_interval)
            if frequency is None:
                return
            if deadline is not None:
                window = max(deadline - loop.time(), 0.0)
                if window == 0:
                    return

        async def arm() -> None:
            await self.find_rf_packet(frequency)

        kind = SignalKind.RF_315 if frequency < 400 else SignalKind.RF_433
        inner = self._capture_loop(
            arm,
            window,
            stop_after_first,
            poll_interval,
            rearm_interval,
            kind,
            frequency,
            claim=False,
        )
        async with contextlib.aclosing(inner):
            async for signal in inner:
                yield signal

    async def _sweep(self, deadline: float | None, poll_interval: float) -> float | None:
        """Sweep for the remote's carrier; return it in MHz, or None if the
        window ran out first."""
        loop = asyncio.get_running_loop()
        await self.sweep_frequency()
        generation = self._tx_generation
        while True:
            now = loop.time()
            if deadline is not None and now >= deadline:
                await self.cancel_sweep_frequency()
                return None
            delay = poll_interval
            if deadline is not None:
                delay = min(delay, deadline - now)
            await asyncio.sleep(delay)
            if generation != self._tx_generation:
                await self.sweep_frequency()
                generation = self._tx_generation
                continue
            found, frequency = await self.check_frequency()
            if found:
                return frequency

    async def check_sensors(self) -> dict:
        """Return the state of the sensors."""
        resp = await self._send(0x1)
        temp = struct.unpack("<bb", resp[:0x2])
        return {"temperature": temp[0x0] + temp[0x1] / 10.0}

    async def check_temperature(self) -> float:
        """Return the temperature."""
        return (await self.check_sensors())["temperature"]


class rmminib(rmmini):
    """Controls a Broadlink RM mini 3 (new firmware)."""

    TYPE = "RMMINIB"

    async def _send(self, command: int, data: bytes = b"") -> bytes:
        """Send a packet to the device."""
        packet = struct.pack("<HI", len(data) + 4, command) + data
        resp = await self.send_packet(0x6A, packet)
        e.check_error(resp[0x22:0x24])
        payload = self.decrypt(resp[0x38:])
        p_len = struct.unpack("<H", payload[:0x2])[0]
        return payload[0x6 : p_len + 2]


class rm4mini(rmminib):
    """Controls a Broadlink RM4 mini."""

    TYPE = "RM4MINI"

    async def check_sensors(self) -> dict:
        """Return the state of the sensors."""
        resp = await self._send(0x24)
        temp = struct.unpack("<bb", resp[:0x2])
        return {
            "temperature": temp[0x0] + temp[0x1] / 100.0,
            "humidity": resp[0x2] + resp[0x3] / 100.0,
        }

    async def check_temperature(self) -> float:
        """Return the temperature."""
        return (await self.check_sensors())["temperature"]

    async def check_humidity(self) -> float:
        """Return the humidity."""
        return (await self.check_sensors())["humidity"]


class rm4pro(rm4mini, rmpro):
    """Controls a Broadlink RM4 pro."""

    TYPE = "RM4PRO"


class rm(rmpro):
    """For backwards compatibility."""

    TYPE = "RM2"


class rm4(rm4pro):
    """For backwards compatibility."""

    TYPE = "RM4"


class rm5plus(rmminib, rmpro):
    """Controls a Broadlink RM5 Plus.

    Mini-b framing from ``rmminib`` (IR) plus RF sweep/capture from
    ``rmpro``, matching the RM5 Plus's marketed IR+RF capabilities.

    Deliberately does *not* inherit ``rm4mini``'s sensor support: on real
    hardware ``check_sensors()`` (command 0x24) answers cleanly but with a
    constant ``{"temperature": 0.0, "humidity": 0.0}``, i.e. this unit has
    no working temperature/humidity sensor over that command. RF itself is
    still unverified against real hardware.
    """

    TYPE = "RM5PLUS"
