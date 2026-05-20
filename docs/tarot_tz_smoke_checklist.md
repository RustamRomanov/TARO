# ASTROV Tarot TZ Smoke Checklist

**Project docs index (April 2026):** [README.md](./README.md).

Purpose: quick regression pass after Tarot animation/AI prompt changes without risky refactoring.

## 1) Build and syntax

- Frontend build: `cd frontend && npm run build`
- Backend syntax: `python3 -m py_compile app/api/tarot_routes.py`

## 2) Visual smoke (manual, Telegram WebApp)

Run one draw for each spread:

- `single`
- `three_cards`
- `financial`
- `six_cards`
- `ten_cards`

Check for each:

- Cards appear via fade/scale/3D flip.
- Reversed cards are visibly rotated.
- Analysis cue appears ("Идёт анализ...") before results.
- No obvious background jerk during card animation.
- "Поделиться" and "Вернуться" buttons work.

## 3) Spread-specific checks

- `single`:
  - One centered card, cinematic reveal.
  - Interpretation text centered below card.

- `three_cards`:
  - Three cards in row with position labels.
  - Swipe between 3 card interpretations and final summary.

- `financial`:
  - Stair geometry.
  - Gold spark effect and gold sound cue.

- `six_cards`:
  - Relationship schema geometry.
  - Pulse-heart effect after final reveal.

- `ten_cards`:
  - Celtic layout with center cross + right column.
  - Column glow then overall glow.
  - Card 2 can be toggled for easier reading orientation.

## 4) Card interaction checks

- Tap card thumbnail opens details modal.
- Pinch zoom / enlarged overlay works in result screens.
- Zoom closes correctly and does not block navigation.

## 5) Backend response contract checks (`/api/tarot/draw-batch`)

- For each spread, response contains:
  - `cards`
  - `cards_interpretations`
  - `summary`
  - `overall`
  - `advice`
- `overall` is not empty fallback when AI provides value.
- `position_name` values map to selected spread positions.

## 6) Known safe constraint for now

Legacy function `FanDeckPick` is still present in `frontend/src/pages/Tarot.jsx` but is not used in the current cinematic runtime path.
