from __future__ import annotations
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_BRIGHTNESS_STEP,
    ATTR_BRIGHTNESS_STEP_PCT,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN, TITLE

class NormalizeProxyLight(LightEntity):
    _attr_should_poll = False
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, hass: HomeAssistant, name: str, target_entity_id: str):
        self.hass = hass
        self._attr_name = name
        self._target = target_entity_id
        self._is_on = False
        self._brightness = 0  # virtual domain 0-255

    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def brightness(self) -> int | None:
        return self._brightness if self._is_on else None

    @property
    def device_info(self) -> DeviceInfo | None:
        return DeviceInfo(
            identifiers={(DOMAIN, f"proxy_{self._target}")},
            name=f"{TITLE} Proxy",
            manufacturer="Community",
            model="NormalizeProxyLight"
        )

    async def async_turn_on(self, **kwargs) -> None:
        # Base virtual value from absolute or current
        v = kwargs.get(ATTR_BRIGHTNESS, self._brightness or 0)

        # Relative steps (Implementation Detail #1)
        if ATTR_BRIGHTNESS_STEP in kwargs:
            v = (self._brightness or 0) + int(kwargs[ATTR_BRIGHTNESS_STEP])
        elif ATTR_BRIGHTNESS_STEP_PCT in kwargs:
            step = int(255 * (kwargs[ATTR_BRIGHTNESS_STEP_PCT] / 100))
            v = (self._brightness or 0) + step

        # Clamp virtual domain and set local state
        v = max(0, min(255, int(v)))
        self._brightness = v
        self._is_on = v > 0

        # TODO: Transform v (virtual) -> a (actual) via engine and call underlying service
        data = {}
        # Example: data["brightness"] = actual_value
        if ATTR_TRANSITION in kwargs:
            data["transition"] = kwargs[ATTR_TRANSITION]

        # TODO: await self.hass.services.async_call("light", "turn_on", {"entity_id": self._target, **data})

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._is_on = False
        self._brightness = 0
        # TODO: await self.hass.services.async_call("light", "turn_off", {"entity_id": self._target, **kwargs})
        self.async_write_ha_state()
