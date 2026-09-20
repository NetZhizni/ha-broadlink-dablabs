"""Support for climate control."""

from collections.abc import Sequence

from . import exceptions as e
from .device import Device
from .helpers import CRC16


class hysen(Device):
    """Controls a Hysen heating thermostat.

    This device is manufactured by Hysen and sold under different
    brands, including Floureon, Beca Energy, Beok and Decdeal.
    """

    TYPE = "HYS"

    async def send_request(self, request: Sequence[int]) -> bytes:
        """Send a request to the device."""
        packet = bytearray()
        packet.extend((len(request) + 2).to_bytes(2, "little"))
        packet.extend(request)
        packet.extend(CRC16.calculate(request).to_bytes(2, "little"))

        response = await self.send_packet(0x6A, packet)
        e.check_error(response[0x22:0x24])
        payload = self.decrypt(response[0x38:])

        p_len = int.from_bytes(payload[:0x02], "little")
        nom_crc = int.from_bytes(payload[p_len : p_len + 2], "little")
        real_crc = CRC16.calculate(payload[0x02:p_len])

        if nom_crc != real_crc:
            raise e.DataValidationError(
                -4008,
                "Received data packet check error",
                f"Expected a checksum of {nom_crc} and received {real_crc}",
            )

        return payload[0x02:p_len]

    def _decode_temp(self, payload, base_index):
        base_temp = payload[base_index] / 2.0
        add_offset = (payload[4] >> 3) & 1
        offset_raw_value = (payload[17] >> 4) & 3
        offset = (offset_raw_value + 1) / 10 if add_offset else 0.0
        return base_temp + offset

    async def get_temp(self) -> float:
        """Return the room temperature in degrees celsius."""
        payload = await self.send_request([0x01, 0x03, 0x00, 0x00, 0x00, 0x08])
        return self._decode_temp(payload, 5)

    async def get_external_temp(self) -> float:
        """Return the external temperature in degrees celsius."""
        payload = await self.send_request([0x01, 0x03, 0x00, 0x00, 0x00, 0x08])
        return self._decode_temp(payload, 18)

    async def get_full_status(self) -> dict:
        """Return the state of the device, timer schedule included."""
        payload = await self.send_request([0x01, 0x03, 0x00, 0x00, 0x00, 0x16])
        data = {}
        data["remote_lock"] = payload[3] & 1
        data["power"] = payload[4] & 1
        data["active"] = (payload[4] >> 4) & 1
        data["temp_manual"] = (payload[4] >> 6) & 1
        data["heating_cooling"] = (payload[4] >> 7) & 1
        data["room_temp"] = self._decode_temp(payload, 5)
        data["thermostat_temp"] = payload[6] / 2.0
        data["auto_mode"] = payload[7] & 0x0F
        data["loop_mode"] = payload[7] >> 4
        data["sensor"] = payload[8]
        data["osv"] = payload[9]
        data["dif"] = payload[10]
        data["svh"] = payload[11]
        data["svl"] = payload[12]
        data["room_temp_adj"] = int.from_bytes(payload[13:15], "big", signed=True) / 10.0
        data["fre"] = payload[15]
        data["poweron"] = payload[16]
        data["unknown"] = payload[17]
        data["external_temp"] = self._decode_temp(payload, 18)
        data["hour"] = payload[19]
        data["min"] = payload[20]
        data["sec"] = payload[21]
        data["dayofweek"] = payload[22]

        weekday = []
        for i in range(0, 6):
            weekday.append(
                {
                    "start_hour": payload[2 * i + 23],
                    "start_minute": payload[2 * i + 24],
                    "temp": payload[i + 39] / 2.0,
                }
            )

        data["weekday"] = weekday
        weekend = []
        for i in range(6, 8):
            weekend.append(
                {
                    "start_hour": payload[2 * i + 23],
                    "start_minute": payload[2 * i + 24],
                    "temp": payload[i + 39] / 2.0,
                }
            )

        data["weekend"] = weekend
        return data

    async def set_mode(self, auto_mode: int, loop_mode: int, sensor: int = 0) -> None:
        """Set the mode of the device."""
        mode_byte = ((loop_mode + 1) << 4) + auto_mode
        await self.send_request([0x01, 0x06, 0x00, 0x02, mode_byte, sensor])

    async def set_advanced(
        self,
        loop_mode: int,
        sensor: int,
        osv: int,
        dif: int,
        svh: int,
        svl: int,
        adj: float,
        fre: int,
        poweron: int,
    ) -> None:
        """Set advanced options."""
        await self.send_request(
            [
                0x01,
                0x10,
                0x00,
                0x02,
                0x00,
                0x05,
                0x0A,
                loop_mode,
                sensor,
                osv,
                dif,
                svh,
                svl,
                int(adj * 10) >> 8 & 0xFF,
                int(adj * 10) & 0xFF,
                fre,
                poweron,
            ]
        )

    async def switch_to_auto(self) -> None:
        """Switch mode to auto."""
        await self.set_mode(auto_mode=1, loop_mode=0)

    async def switch_to_manual(self) -> None:
        """Switch mode to manual."""
        await self.set_mode(auto_mode=0, loop_mode=0)

    async def set_temp(self, temp: float) -> None:
        """Set the target temperature."""
        await self.send_request([0x01, 0x06, 0x00, 0x01, 0x00, int(temp * 2)])

    async def set_power(
        self, power: int = 1, remote_lock: int = 0, heating_cooling: int = 0
    ) -> None:
        """Set the power state of the device."""
        state = (heating_cooling << 7) + power
        await self.send_request([0x01, 0x06, 0x00, 0x00, remote_lock, state])

    async def set_time(self, hour: int, minute: int, second: int, day: int) -> None:
        """Set the time. day=1 is Monday, ..., day=7 is Sunday."""
        await self.send_request(
            [0x01, 0x10, 0x00, 0x08, 0x00, 0x02, 0x04, hour, minute, second, day]
        )

    async def set_schedule(self, weekday: list[dict], weekend: list[dict]) -> None:
        """Set timer schedule."""
        request = [0x01, 0x10, 0x00, 0x0A, 0x00, 0x0C, 0x18]

        for i in range(0, 6):
            request.append(weekday[i]["start_hour"])
            request.append(weekday[i]["start_minute"])

        for i in range(0, 2):
            request.append(weekend[i]["start_hour"])
            request.append(weekend[i]["start_minute"])

        for i in range(0, 6):
            request.append(int(weekday[i]["temp"] * 2))

        for i in range(0, 2):
            request.append(int(weekend[i]["temp"] * 2))

        await self.send_request(request)
