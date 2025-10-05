
# Normalize Lights — DESIGN.md (Starter)

**One‑liner:** Normalizes lighting attributes (currently brightness) so a single scalar control yields consistent visible results across mixed devices.

## 1. Purpose & Goals
- Provide virtual `light` entities that apply per‑fixture transforms so mixed hardware behaves consistently to a single brightness scalar.
- Keep normalization logic centralized and extensible to future attributes (color/CT).
- Avoid helper bloat; operate like first‑class light entities.

## 2. Scope (v1) / Non‑Goals
**In scope (v1):**
- Proxy light per physical light (on/off, brightness, transition pass‑through).
- Optional room‑level light controlling multiple proxies.
- Per‑fixture parameters: LLV, HLD, curve profile (initially identity/linear placeholder).
- Relative steps: `brightness_step`, `brightness_step_pct`.
- Reverse sync when target light changes externally.
- Loop prevention (context handling).

**Non‑goals (v1):**
- Color/CT normalization (future).
- Vendor‑specific calibration wizards (future).
- Scene management beyond native HA scenes.

## 3. Architecture (high level)
- Domain: `normalize_lights` (custom integration).
- Platform: `light` (entities shown as `light.*`).
- Entities:
  - **Proxy Light:** wraps one real light; maps virtual↔actual brightness.
  - **Room Light (optional):** fans out a virtual scalar to member proxies.
- Data:
  - ConfigEntry holds per‑proxy params (target entity, LLV, HLD, curve).
  - Internal transform engine module: `virtual→actual`, `actual→virtual`.

## 4. Transforms (initial contract)
- **Virtual domain:** 0–255 (HA brightness scalar).
- **Actual domain:** 0–255 (target’s brightness attribute).
- Functions:
  - `virtual_to_actual(v, llv, hld, profile) -> int`
  - `actual_to_virtual(a, llv, hld, profile) -> int`
- Rules:
  - Clamp inputs/outputs to `[0,255]`.
  - Define rounding (floor to int).
  - Identity profile for M1–M2 (IMT), add linear/gamma later.

### Example test vectors (placeholder)
| v | llv | hld | expected a |
|---|-----|-----|------------|
| 0 | 10  | 210 | 0          |
| 128 | 10 | 210 | ~ (linear mid) |
| 255 | 10 | 210 | 255        |

## 5. Event Flows (bullet sketches)
- **User → Proxy → Target:** set `brightness` → transform v→a → call `light.turn_on` on target (with `brightness`, `transition` if given) → update Proxy state.
- **Target → Proxy (reverse):** target attribute changes → compute a→v → update Proxy state; ignore self‑originated updates via context.
- **Room Light:** set or step virtual brightness → compute per‑member a values → fan‑out to members → aggregate room state (v1: last‑set).

## 6. Config & Options
- ConfigEntry per proxy:
  - `name`, `target_entity_id`, `llv`, `hld`, `curve_profile` (default: identity).
- Options Flow lets editing of `llv`, `hld`, `curve_profile`.
- Room Light (optional): members (list of proxy entities), aggregation strategy (v1: last‑set).

## 7. Errors & Resilience
- Target unavailable: mark proxy `available = False`.
- Unsupported brightness on target: expose only on/off.
- Service failures: log warning; retry on next command.
- Transition handling: pass‑through if supported; emulate basic tween otherwise.

## 8. IMT Milestones (acceptance gates)
- **M1:** Proxy loads; on/off only; identity state.
- **M2:** Absolute `brightness` supported; identity transform; calls target.
- **M3:** Relative steps (`brightness_step(_pct)`); clamp; compute absolute before calling target.
- **M4:** Reverse sync; loop prevention with context.
- **M5:** Optional Room Light fan‑out; aggregation = last‑set.
- **M6:** Transitions pass‑through; basic tween emulation for unsupported devices.

## 9. Test Plan (outline)
- Unit: transform function round‑trip; clamp/edges; step arithmetic.
- Integration: proxy on/off/brightness; reverse update; context loop guard; room fan‑out.
- Smoke: HA loads integration; entities register; minimal config flow loads.
