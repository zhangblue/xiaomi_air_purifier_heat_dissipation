"""Local-network control for the confirmed Xiaomi Air Purifier Pro model."""

import miio
from miio.integrations.airpurifier.zhimi.airpurifier import OperationMode


class PurifierError(RuntimeError):
    """The purifier could not be controlled or did not confirm the target state."""


class MiioPurifier:
    """Apply and verify Favorite mode commands on a single purifier."""

    def __init__(self, device, *, expected_model: str):
        self._device = device
        info = self._call("read device information", device.info)
        try:
            model = info.model
        except Exception:
            raise PurifierError("Could not read purifier model") from None
        if model != expected_model:
            raise PurifierError("Purifier model does not match expected model")

    @classmethod
    def from_host(cls, host: str, token: str, *, expected_model: str):
        """Construct a real python-miio device and verify its reported model."""
        try:
            device = miio.AirPurifier(host, token)
        except Exception:
            raise PurifierError("Could not create purifier connection") from None
        return cls(device, expected_model=expected_model)

    @staticmethod
    def _call(action, method, *args):
        try:
            return method(*args)
        except Exception:
            raise PurifierError(f"Could not {action}") from None

    def _readback(self, level: int):
        status = self._call("read purifier status", self._device.status)
        try:
            confirmed = (status.is_on and status.mode == OperationMode.Favorite
                         and status.favorite_level == level)
        except Exception:
            raise PurifierError("Could not interpret purifier status") from None
        if not confirmed:
            raise PurifierError("Purifier did not confirm Favorite mode and level")
        return status

    def start(self, level: int):
        """Power on, set the Favorite level and mode, then verify the result."""
        self._call("power on purifier", self._device.on)
        self._call("set Favorite level", self._device.set_favorite_level, level)
        self._call("set Favorite mode", self._device.set_mode,
                   OperationMode.Favorite)
        return self._readback(level)

    def set_level(self, level: int):
        """Change only the Favorite level, then verify power, mode and level."""
        self._call("set Favorite level", self._device.set_favorite_level, level)
        return self._readback(level)
