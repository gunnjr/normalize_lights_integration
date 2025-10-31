# custom_components/normalize_lights/config_flow.py
from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector as sel
from homeassistant.helpers import entity_registry as er
import voluptuous as vol

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
# Note: Profile selection is disabled for v1 - linear mapping only
# PROFILE_OPTIONS = ["linear"]  # reserved for future curves


def _parse_level(value: Any) -> int | None:
    """Accepts '35%', 35, '204', 204; returns 0..255 or None."""
    def clamp255(n):
        try:
            n = float(n)
        except (TypeError, ValueError):
            return None
        n = max(0.0, min(255.0, n))
        return int(round(n))

    if value is None:
        return None

    if isinstance(value, str):
        s = value.strip()
        if s.endswith("%"):
            try:
                pct = float(s[:-1].strip())
            except ValueError:
                return None
            if not (0.0 <= pct <= 100.0):
                return None
            return clamp255(255.0 * (pct / 100.0))
        try:
            v = float(s)
        except ValueError:
            return None
        if 0.0 <= v <= 100.0:
            return clamp255(255.0 * (v / 100.0))
        return clamp255(v)

    if isinstance(value, (int, float)):
        v = float(value)
        if 0.0 <= v <= 100.0:
            return clamp255(255.0 * (v / 100.0))
        return clamp255(v)

    return None


def _derive_default_name(hass: HomeAssistant, target: str) -> str:
    st = hass.states.get(target)
    if st:
        base = st.attributes.get("friendly_name") or target.split(".", 1)[-1]
    else:
        base = target.split(".", 1)[-1]
    return f"{base} (Normalized)"


def _derive_default_object_id(target: str) -> str:
    return f"{target.split('.', 1)[-1]}_proxy"  # e.g., light.mba_s1_2 -> mba_s1_2_proxy


class NormalizeLightsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        """Initialize config flow."""
        self.target_entity = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step - target selection."""
        _LOGGER.debug("normalize_lights: async_step_user called with input: %s", user_input)
        errors: dict[str, str] = {}

        if user_input is not None:
            target: str = user_input["target"].strip()
            _LOGGER.debug("normalize_lights: validating target: %s", target)
            
            # Validate target is a *non-proxy* light
            if await self._is_proxy_light(self.hass, target):
                _LOGGER.debug("normalize_lights: target is proxy light")
                errors["base"] = "target_is_proxy"
            elif await self._target_already_proxied(self.hass, target):
                _LOGGER.debug("normalize_lights: target already has proxy")
                errors["base"] = "target_in_use"
            
            if not errors:
                _LOGGER.debug("normalize_lights: target validation passed, proceeding to configure step")
                self.target_entity = target
                return await self.async_step_configure()

        _LOGGER.debug("normalize_lights: showing target selection form")
        # Show target selection form
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("target"): sel.selector({"entity": {"domain": "light"}}),
            }),
            errors=errors,
        )

    async def async_step_configure(self, user_input: dict[str, Any] | None = None):
        """Handle the configuration step with auto-populated defaults."""
        errors: dict[str, str] = {}

        # Generate defaults based on selected target
        suggested_name = _derive_default_name(self.hass, self.target_entity)
        suggested_object_id = _derive_default_object_id(self.target_entity)

        if user_input is not None:
            proxy_object_id_in: str = (user_input.get("proxy_object_id") or "").strip()
            name_in: str = (user_input.get("name") or "").strip()

            # Convert LLV/HLD into 0..255
            llv = _parse_level(user_input["llv"])
            hld = _parse_level(user_input["hld"])

            if llv is None or hld is None:
                errors["base"] = "bad_level"
            elif llv > hld:
                errors["base"] = "llv_gt_hld"

            if not errors:
                # Use custom name if provided, otherwise leave None for auto-generation
                name = name_in if name_in else None
                proxy_object_id = proxy_object_id_in or suggested_object_id
                _LOGGER.debug("normalize_lights: final values - name: %s, proxy_object_id: %s (input: %s, suggested: %s)", 
                             name, proxy_object_id, proxy_object_id_in, suggested_object_id)

                data = {
                    "name": name,
                    "target": self.target_entity,
                    "proxy_object_id": proxy_object_id,
                    "llv": llv,
                    "hld": hld,
                    "profile": "linear",  # Fixed value for v1
                }
                _LOGGER.debug("normalize_lights: creating config entry with data: %s", data)
                # Use custom name for config entry title, or fall back to suggested name
                entry_title = name if name else suggested_name
                return self.async_create_entry(title=entry_title, data=data)

        # Show configuration form with pre-populated defaults
        return self.async_show_form(
            step_id="configure",
            data_schema=vol.Schema({
                vol.Optional("name", default=""): str,  # Leave blank by default
                vol.Optional("proxy_object_id", default=suggested_object_id): str,
                vol.Required("llv", default="17%"): str,
                vol.Required("hld", default="94%"): str,
            }),
            errors=errors,
            description_placeholders={
                "target_entity": self.target_entity,
                "llv_help": "LLV: Minimum brightness that produces visible light (e.g., 17%)\nHLD: Maximum brightness before full intensity (e.g., 94%)\n\nAccepts percentages (17%) or raw values (0-255)",
            },
        )

    async def _target_already_proxied(self, hass: HomeAssistant, target: str) -> bool:
        for entry in hass.config_entries.async_entries(DOMAIN):
            if entry.data.get("target") == target:
                return True
        return False

    async def _is_proxy_light(self, hass: HomeAssistant, entity_id: str) -> bool:
        """Heuristic: exclude our own proxies and anything ending '_proxy'."""
        if entity_id.split(".", 1)[-1].endswith("_proxy"):
            return True
        registry = er.async_get(hass)
        ent = registry.async_get(entity_id)
        # If the entity is provided by OUR integration, treat it as a proxy.
        return bool(ent and ent.platform == DOMAIN)