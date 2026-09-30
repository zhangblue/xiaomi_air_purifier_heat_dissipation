"""Local-network control for the confirmed Xiaomi Air Purifier Pro model."""

import miio
from miio.integrations.airpurifier.zhimi.airpurifier import OperationMode


class PurifierError(RuntimeError):
    """The purifier could not be controlled or did not confirm the target state."""


class PurifierLevelRejected(PurifierError):
    """The purifier explicitly declined a Favorite level command."""


class PurifierModelMismatch(PurifierError):
    """The connected device is not the configured purifier model."""


class MiioPurifier:
    """Apply and verify Favorite mode commands on a single purifier."""

    def __init__(self, device, *, expected_model: str, verify: bool = True):
        self._device = device
        self._expected_model = expected_model
        if verify:
            self.verify_model()

    def verify_model(self):
        """Read and validate the device model without changing device state."""
        info = self.read_info()
        try:
            model = info.model
        except Exception:
            raise PurifierError("Could not read purifier model") from None
        if model != self._expected_model:
            raise PurifierModelMismatch("Purifier model does not match expected model")
        return info

    @classmethod
    def from_host(cls, host: str, token: str, *, expected_model: str,
                  verify: bool = True):
        """Construct a real device; optionally verify its reported model."""
        try:
            device = miio.AirPurifier(host, token)
        except Exception:
            raise PurifierError("Could not create purifier connection") from None
        return cls(device, expected_model=expected_model, verify=verify)

    @staticmethod
    def _call(action, method, *args):
        try:
            return method(*args)
        except Exception:
            raise PurifierError(f"Could not {action}") from None

    def _readback(self, level: int):
        status = self.read_status()
        try:
            powered_and_favorite = status.is_on and status.mode == OperationMode.Favorite
            actual_level = status.favorite_level
        except Exception:
            raise PurifierError("Could not interpret purifier status") from None
        if not powered_and_favorite:
            raise PurifierError("Purifier did not confirm Favorite mode and level")
        if actual_level != level:
            raise PurifierError("Purifier did not yet confirm Favorite level")
        return status

    def read_info(self):
        """Read device information without changing purifier state."""
        return self._call("read device information", self._device.info)

    def read_status(self):
        """Read the current purifier state without sending control commands."""
        return self._call("read purifier status", self._device.status)

    def start(self, level: int):
        """Power on, set the Favorite level and mode, then verify the result."""
        self._call("power on purifier", self._device.on)
        if self._call("set Favorite level", self._device.set_favorite_level, level) is False:
            raise PurifierLevelRejected("Purifier rejected Favorite level")
        self._call("set Favorite mode", self._device.set_mode,
                   OperationMode.Favorite)
        return self._readback(level)

    def set_level(self, level: int):
        """Change only the Favorite level, then verify power, mode and level."""
        if self._call("set Favorite level", self._device.set_favorite_level, level) is False:
            raise PurifierLevelRejected("Purifier rejected Favorite level")
        return self._readback(level)
