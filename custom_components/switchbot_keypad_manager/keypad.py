"""BLE commands to enroll and delete credentials on a SwitchBot Keypad Vision / Vision Pro.

Commands are sent through the device object of Home Assistant's SwitchBot integration, which already
handles the encryption key, Bluetooth proxies and AES-CTR framing. See docs/PROTOCOL.md for details.

Command group (byte after 570F52): 02 PIN, 03 NFC, 04 fingerprint, 05 face, 06 palm.
Verified on a Keypad Vision Pro: PIN, fingerprint and face enroll/delete. Palm confirm/delete follow the
face scheme and are not verified yet.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
import secrets
import time

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import FACE, FINGERPRINT, NFC, PALM, PIN

_LOGGER = logging.getLogger(__name__)

BUSY = b"\x09"
ENROLL_SECONDS = 90
DELETE = {PIN: "570F520205", NFC: "570F520304", FINGERPRINT: "570F520403", FACE: "570F520503", PALM: "570F520603"}


class KeypadError(HomeAssistantError):
    """Connection or protocol error talking to the keypad."""


def _h(n: int) -> str:
    return f"{n & 0xFF:02X}"


def _ts(seconds: float) -> str:
    return f"{int(seconds) & 0xFFFFFFFF:08X}"


class Keypad:
    """Talks to one Keypad Vision (Pro) through the SwitchBot integration."""

    def __init__(self, hass: HomeAssistant, switchbot_entry_id: str) -> None:
        self.hass = hass
        self.entry_id = switchbot_entry_id
        self.lock = asyncio.Lock()

    def _device(self):
        entry = self.hass.config_entries.async_get_entry(self.entry_id)
        if entry is None or entry.state is not ConfigEntryState.LOADED or getattr(entry, "runtime_data", None) is None:
            raise KeypadError("Keypad is not loaded in the SwitchBot integration")
        return entry.runtime_data.device

    async def command(self, hexcmd: str, attempts: int = 4) -> bytes:
        """Send a command; a 'busy' (09) reply is retried."""
        device = self._device()
        for i in range(attempts):
            try:
                reply = await device._send_command(hexcmd)  # noqa: SLF001
            except Exception as err:  # noqa: BLE001 - any Bluetooth error
                _LOGGER.debug("Command %s failed: %s", hexcmd[:12], err)
                reply = None
            if reply and reply != BUSY:
                return reply
            await asyncio.sleep(2 + i * 2)
        raise KeypadError("Keypad does not respond (out of range or busy)")

    async def _status(self) -> bytes | None:
        """Enrollment status; BUSY while the keypad is scanning, None on no answer."""
        try:
            return await self._device()._send_command("570F530106")  # noqa: SLF001
        except Exception:  # noqa: BLE001
            return None

    async def counts(self) -> dict[str, int]:
        data = await self.command("570F530100")
        if data[0] != 1 or len(data) < 6:
            raise KeypadError(f"Unexpected count reply: {data.hex()}")
        result = {PIN: data[1], NFC: data[2], FINGERPRINT: data[3], "duress_pin": data[4], "duress_fingerprint": data[5]}
        if len(data) >= 8:
            result[FACE] = data[6]
            result[PALM] = data[7]
        return result

    async def delete(self, kind: str, slot: int) -> None:
        async with self.lock:
            data = await self.command(DELETE[kind] + _h(slot))
            if data[0] != 1:
                raise KeypadError(f"Keypad refused the deletion ({data.hex()})")

    async def enroll(self, kind: str, *, valid_from: float | None = None, valid_until: float | None = None,
                     once: bool = False, status: Callable[[str], Awaitable[None] | None] | None = None,
                     cancel: asyncio.Event | None = None) -> dict:
        """Enroll a new credential. Returns {'slot': n, 'pin': '…' (PIN only)}.

        `status` receives short keys: finger, face, palm, card, pin_done.
        """
        async def report(key: str) -> None:
            if status:
                result = status(key)
                if asyncio.iscoroutine(result):
                    await result

        limited = valid_from is not None and valid_until is not None
        async with self.lock:
            before = None
            if kind != PIN:
                try:
                    before = (await self.counts()).get(kind)
                except KeypadError:
                    before = None
            if kind == PIN:
                return await self._pin(limited, once, valid_from, valid_until, report)
            if kind == FINGERPRINT:
                data = await self.command("570F520401" + ("01" if limited else "00") + "0200")
                if data[0] != 1:
                    raise KeypadError(f"Keypad did not start the enrollment ({data.hex()})")
                slot = data[1]
                if limited:
                    await self.command(f"570F520402{_h(slot)}{_ts(valid_from)}{_ts(valid_until)}")
                await report("finger")
                outcome = await self._wait(
                    # byte 3: high nibble = captures so far, low nibble = result (0 running, 1 complete, 3 exists).
                    # Observed: 10, 20, 30 while capturing, 31 when complete - "30" is NOT finished yet.
                    duplicate=lambda a: len(a) > 3 and a[0] == 1 and (a[3] & 0x0F) == 3,
                    done=lambda a: len(a) > 3 and a[0] == 1 and (a[3] & 0x0F) == 1 and (a[3] >> 4) >= 3,
                    progress=lambda a: len(a) > 3 and a[0] == 1 and (a[3] & 0x0F) == 0,
                    cancel=cancel)
                if outcome != "done":
                    await self._cleanup(FINGERPRINT, slot)
                    raise KeypadError(self._reason(outcome, "This finger is already enrolled"))
                await self.command(f"570F520405{_h(slot)}")
                await self._verify(FINGERPRINT, slot, before)
                return {"slot": slot}
            if kind in (FACE, PALM):
                group = "05" if kind == FACE else "06"
                await self.command(f"570F52{group}06")       # end a previous enrollment
                data = await self.command(f"570F52{group}010002")
                if data[0] != 1:
                    raise KeypadError(f"Keypad did not start the enrollment ({data.hex()})")
                slot = data[1]
                await report("face" if kind == FACE else "palm")
                outcome = await self._wait(done=lambda a: len(a) > 5 and a[0] == 1 and a[5] == 1, cancel=cancel)
                if outcome != "done":
                    await self._cleanup(kind, slot)
                    raise KeypadError(self._reason(outcome, ""))
                await self.command(f"570F52{group}05{_h(slot)}")
                await self._verify(kind, slot, before)
                return {"slot": slot}
            if kind == NFC:
                data = await self.command("570F520301" + ("01" if limited else "00") + "02")
                if data[0] != 1:
                    raise KeypadError(f"Keypad did not start the enrollment ({data.hex()})")
                slot = data[1]
                await report("card")
                outcome = await self._wait(
                    duplicate=lambda a: len(a) > 2 and a[0] == 1 and a[2] == 3,
                    done=lambda a: len(a) > 2 and a[0] == 1 and a[2] == 1,
                    failed=lambda a: len(a) > 2 and a[0] == 1 and a[2] in (2, 4), cancel=cancel)
                if outcome != "done":
                    await self._cleanup(NFC, slot)
                    raise KeypadError(self._reason(outcome, "This card is already enrolled"))
                if limited:
                    await self.command(f"570F520303{_h(slot)}{_ts(valid_from)}{_ts(valid_until)}")
                await self.command(f"570F520307{_h(slot)}")
                await self._verify(NFC, slot, before)
                return {"slot": slot}
        raise KeypadError(f"Unknown credential kind {kind}")

    async def _pin(self, limited, once, valid_from, valid_until, report) -> dict:
        pin = "".join(str(secrets.randbelow(10)) for _ in range(6))
        pin_type = 2 if once else (1 if limited else 0)
        payload = bytes([0xFF, pin_type, len(pin)]) + bytes(int(c) for c in pin)
        chunks = [payload[i:i + 11] for i in range(0, len(payload), 11)]
        data = b""
        for i, chunk in enumerate(chunks):
            data = await self.command("570F520202" + _h((len(chunks) << 4) | i) + chunk.hex().upper())
            if data[0] != 1:
                raise KeypadError(f"Keypad refused the PIN ({data.hex()})")
        slot = data[2] if len(data) > 2 else data[1]
        if limited:
            await self.command(f"570F520203{_h(slot)}{_ts(valid_from)}{_ts(valid_until)}")
        await report("pin_done")
        return {"slot": slot, "pin": pin}

    async def _verify(self, kind: str, slot: int, before: int | None) -> None:
        """Make sure the keypad really stored the credential (its count went up)."""
        if before is None:
            return
        for _ in range(3):
            try:
                after = (await self.counts()).get(kind)
            except KeypadError:
                after = None
            _LOGGER.debug("Verify %s slot %s: count %s -> %s", kind, slot, before, after)
            if after is not None and after > before:
                return
            await asyncio.sleep(2)
        await self._cleanup(kind, slot)
        raise KeypadError("The keypad did not store the credential – please try again")

    async def _wait(self, *, done, duplicate=None, failed=None, progress=None, cancel=None,
                    need_busy=True) -> str:
        """Poll the enrollment status until done/duplicate/failed/timeout.

        The status register keeps the result of the previous enrollment (e.g. a face), so a result is only accepted
        after the keypad has reported busy (scanning) during this enrollment, or once the status differs from the
        first (stale) value read after the start.
        """
        start = time.monotonic()
        deadline = start + ENROLL_SECONDS
        seen_busy = not need_busy
        seen_progress = False
        first: bytes | None = None
        while time.monotonic() < deadline:
            if cancel is not None and cancel.is_set():
                return "cancelled"
            reply = await self._status()
            _LOGGER.debug("Enrollment status after %.1f s: %s", time.monotonic() - start,
                          reply.hex() if reply else None)
            if reply and progress and progress(reply):
                seen_progress = True
            if reply == BUSY:
                seen_busy = True
            elif reply and first is None and not seen_busy:
                first = reply
            elif reply and (seen_busy or reply != first):
                # a stale "done" from the previous enrollment needs visible progress first
                if progress and first is not None and done(first) and not seen_progress and done(reply):
                    await asyncio.sleep(1)
                    continue
                if duplicate and duplicate(reply):
                    return "duplicate"
                if failed and failed(reply):
                    return "failed"
                if done(reply):
                    return "done"
            await asyncio.sleep(1)
        return "timeout"

    @staticmethod
    def _reason(outcome: str, duplicate_text: str) -> str:
        return {"duplicate": duplicate_text or "Already enrolled", "cancelled": "Cancelled",
                "failed": "Enrollment failed", "timeout": "Timed out (90 s)"}.get(outcome, outcome)

    async def _cleanup(self, kind: str, slot: int) -> None:
        """Free a half-enrolled slot again."""
        try:
            if kind in (FACE, PALM):
                await self.command(f"570F52{'05' if kind == FACE else '06'}06", attempts=2)
            await self.command(DELETE[kind] + _h(slot), attempts=2)
        except KeypadError:
            _LOGGER.debug("Could not clean up %s slot %s", kind, slot)
