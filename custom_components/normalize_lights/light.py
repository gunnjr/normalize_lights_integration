# custom_components/normalize_lights/light.py

# Optional; remove if you prefer. Must be FIRST if present.
# from __future__ import annotations

import logging
from homeassistant.components.light import (
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Minimal Proxy LightEntity for IMT validation
# -------------------------------------------------------------------
class NormalizeProxyLight(LightEntity):
    """A minimal virtual light that proxies another light."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_is_on = False
    _attr_brightness = 128

    def __init__(self, hass: HomeAssistant, name: str, target_entity: str) -> None:
        self.hass = hass
        self._attr_name = name
        self._target_entity_id = target_entity

    async def async_turn_on(self, **kwargs):
        _LOGGER.debug("normalize_lights: turn_on called %s", kwargs)
        self._attr_is_on = True
        await self.hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": self._target_entity_id, **kwargs},
            blocking=False,
        )
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        _LOGGER.debug("normalize_lights: turn_off called %s", kwargs)
        self._attr_is_on = False
        await self.hass.services.async_call(
            "light",
            "turn_off",
            {"entity_id": self._target_entity_id},
            blocking=False,
        )
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._attr_is_on


# -------------------------------------------------------------------
# YAML Setup Hooks
# -------------------------------------------------------------------
def setup_platform(hass, config, add_entities, discovery_info=None):
    """Sync wrapper for legacy YAML setup."""
    hass.async_create_task(async_setup_platform(hass, config, add_entities, discovery_info))


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Primary async setup for YAML configuration."""
    name = config.get("name") or f"Proxy for {config.get('target', 'unknown')}"
    target = config["target"]

    _LOGGER.warning("normalize_lights: async_setup_platform called for %s → %s", name, target)

    async_add_entities([NormalizeProxyLight(hass, name, target)], update_before_add=False)
