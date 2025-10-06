# custom_components/normalize_lights/light.py
import logging
_LOGGER = logging.getLogger(__name__)

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
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, TITLE
from .engine import virtual_to_actual

# --- YAML platform schema ---
PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA.extend(
    {
        vol.Required("target"): cv.entity_domain("light"),
        vol.Optional("name"): cv.string,
        # future: llv, hld, profile, etc.
    }
)

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Sync wrapper to ensure YAML setup works."""
    _LOGGER.warning("normalize_lights: setup_platform shim called")
    hass.async_create_task(async_setup_platform(hass, config, add_entities, discovery_info))


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    _LOGGER.warning("normalize_lights: async_setup_platform called with %s", config)
    name = config.get("name") or f"Proxy for {config['target']}"
    target = config["target"]
    async_add_entities([NormalizeProxyLight(hass, name, target)], update_before_add=False)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """
    Minimal IMT setup via YAML:
      light:
        - platform: normalize_lights
          name: Desk Proxy
          target: light.desk_real
    """
    name = config.get("name") or f"Proxy for {config['target']}"
    target = config["target"]
    async_add_entities([NormalizeProxyLight(hass, name, target)], update_before_add=False)


class NormalizeProxyLight(LightEntity):
    """Minimal proxy with identity transform (IMT v1)."""

    _attr_should_poll = False
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, hass: HomeAssistant, name: str, target_entity_id: str):
        self.hass = hass
        self._attr_name = name
        self._target = target_entity_id
        self._is_on = False
        self._brightness = 0  # virtual domain 0-255
        self._attr_unique_id = f"{DOMAIN}_{self._target}"

    # ----- HA required properties -----
    @property
    def is_on(self) -> bool:
        return self._is_on

    @property
    def brightness(self) -> int | None:
        return self._brightness if self._is_on else None

    @property
    def supported_color_modes(self):
        return self._attr_supported_color_modes

    @property
    def device_info(self) -> DeviceInfo | None:
        return DeviceInfo(
            identifiers={(DOMAIN, f"proxy_{self._target}")},
            name=f"{TITLE} Proxy",
            manufacturer="Community",
            model="NormalizeProxyLight",
        )

    # ----- Core behavior -----
    async def async_turn_on(self, **kwargs) -> None:
        # Absolute virtual target (default to current)
        v = kwargs.get(ATTR_BRIGHTNESS, self._brightness or 0)

        # Relative steps (Implementation Detail #1)
        if ATTR_BRIGHTNESS_STEP in kwargs:
            v = (self._brightness or 0) + int(kwargs[ATTR_BRIGHTNESS_STEP])
        elif ATTR_BRIGHTNESS_STEP_PCT in kwargs:
            step = int(255 * (kwargs[ATTR_BRIGHTNESS_STEP_PCT] / 100))
            v = (self._brightness or 0) + step

        # Clamp in virtual domain
        v = max(0, min(255, int(v)))

        # IMT v1: identity transform → actual
        a = virtual_to_actual(v)

        data = {"entity_id": self._target, "brightness": a}
        if ATTR_TRANSITION in kwargs:
            data["transition"] = kwargs[ATTR_TRANSITION]

        # Call underlying device
        await self.hass.services.async_call("light", "turn_on", data, blocking=False)

        # Update local proxy state
        self._brightness = v
        self._is_on = v > 0
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        data = {"entity_id": self._target}
        if ATTR_TRANSITION in kwargs:
            data["transition"] = kwargs[ATTR_TRANSITION]

        await self.hass.services.async_call("light", "turn_off", data, blocking=False)

        self._is_on = False
        self._brightness = 0
        self.async_write_ha_state()
