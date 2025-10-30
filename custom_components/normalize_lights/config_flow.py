# custom_components/normalize_lights/config_flow.py
from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector as sel
from homeassistant.helpers import entity_registry as er
import voluptuous as vol

from .const import DOMAIN

PROFILE_OPTIONS = ["linear"]  # reserved for future curves


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
    return f"{base} Proxy"


def _derive_default_object_id(target: str) -> str:
    return f"{target.split('.', 1)[-1]}_proxy"  # e.g., light.mba_s1_2 -> mba_s1_2_proxy


def _schema():
    # Field order is preserved; target first.
    return vol.Schema(
        {
            vol.Required("target"): sel.selector({"entity": {"domain": "light"}}),
            vol.Optional("proxy_object_id", default=""): str,  # suggested entity_id suffix (editable)
            vol.Optional("name", default=""): str,             # display name (optional)
            vol.Required("llv", default="0"): str,             # accepts % or 0–255
            vol.Required("hld", default="255"): str,           # accepts % or 0–255
            vol.Required("profile", default="linear"): vol.In(PROFILE_OPTIONS),
        }
    )


class NormalizeLightsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            target: str = user_input["target"].strip()
            proxy_object_id_in: str = (user_input.get("proxy_object_id") or "").strip()
            name_in: str = (user_input.get("name") or "").strip()
            profile: str = user_input["profile"]

            # Convert LLV/HLD into 0..255
            llv = _parse_level(user_input["llv"])
            hld = _parse_level(user_input["hld"])

            # Validate target is a *non-proxy* light
            if await self._is_proxy_light(self.hass, target):
                errors["base"] = "target_is_proxy"

            if llv is None or hld is None:
                errors["base"] = "bad_level"
            elif llv > hld:
                errors["base"] = "llv_gt_hld"
            elif await self._target_already_proxied(self.hass, target):
                errors["base"] = "target_in_use"

            if not errors:
                name = name_in or _derive_default_name(self.hass, target)
                proxy_object_id = proxy_object_id_in or _derive_default_object_id(target)

                data = {
                    "name": name,
                    "target": target,
                    "proxy_object_id": proxy_object_id,  # used to suggest entity_id
                    "llv": llv,   # stored as 0–255
                    "hld": hld,   # stored as 0–255
                    "profile": profile,
                }
                return self.async_create_entry(title=name, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(),
            errors=errors,
            description_placeholders={
                "llv_help": "Enter 1–99% or 1–254 (raw).",  # shown via translations description
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