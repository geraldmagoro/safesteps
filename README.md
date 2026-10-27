# SafeSteps MVP — Meta Global AI Developer Hackathon

Kids in South Africa walk to school without phones. SafeSteps simulates a
**breathable ankle band worn under a sock** that tracks GPS + heart rate +
skin contact, detects anomalies in real time, and alerts parents fast.

## Layout

```
safesteps/
├── backend/            FastAPI: ingest, status, alert websocket, AI summary
│   ├── main.py
│   └── requirements.txt
├── band-simulator/     Python band sim (stdlib only): normal + anomaly modes
│   └── simulate.py
├── parent-app/         React Native (Expo) parent app: onboarding, live, alert
│   ├── App.js
│   └── src/
└── README.md
```

## Setup

Windows (PowerShell), from this folder:

```powershell
# 1. Python env (project-local, used by backend + simulator)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
# (equivalent: pip install fastapi "uvicorn[standard]" pydantic)

# 2. Parent app
cd parent-app
npm install
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd parent-app && npm install
```

Optional — live AI summaries via the Meta Model API (`muse-wonder-1.0`):

```powershell
$env:META_API_KEY = "<your key from the dashboard>"
$env:META_API_URL = "<model endpoint from the dashboard>"
```

Without these, the backend returns a rule-based summary so the demo
always works offline. Never commit keys — use env vars only.

## Run

Terminal 1 — backend:

```powershell
.venv\Scripts\Activate.ps1
uvicorn backend.main:app --reload --port 8000
```

Terminal 2 — band simulator (normal walk):

```powershell
.venv\Scripts\Activate.ps1
python band-simulator\simulate.py --mode normal
```

Terminal 3 — parent app:

```powershell
cd parent-app
npx expo start
```

Then open the app in Expo Go (same Wi-Fi) or press `w` for web.
On a physical phone, set `BACKEND_URL` in `parent-app/src/api.js`
to your PC's LAN IP (e.g. `http://192.168.1.20:8000`).

## Demo flow (3 minutes)

1. **Normal walk** — simulator `--mode normal`: Home → Spaza (left) →
   School. App map shows LIVE GPS + vitals, no alert.
2. **Off-route** — `python band-simulator\simulate.py --mode offroute --fast 60`
   (6 min compressed to ~6 s): band turns RIGHT at the junction.
   After 5 min off-route the backend fires `off_route`.
3. **Triggers** — try the others:
   - `--mode skinoff` → `skin_off` (gap 3 cm > 2.5 cm)
   - `--mode spike` → `hr_spike_no_movement` (HR 90 → 145, still)
   - `--mode faint` → `possible_faint` (still + HR drop)
   - `--mode demo --fast 20` runs the full reel in ~25 s.
4. Each alert returns
   `{anomaly, type, location, ai_summary, actions}`,
   writes `backend/alert.json` (with 20 s burst placeholders),
   and broadcasts on `ws://localhost:8000/ws/alerts`.
5. **Call All** — in the app, open the alert screen and press
   CALL ALL to dial the 5 emergency contacts, with nearby
   SAPS/clinic numbers and burst clips alongside.

## API reference

| Method | Path                         | Purpose                          |
| ------ | ---------------------------- | -------------------------------- |
| POST   | `/ingest`                    | Band reading → anomaly or ok     |
| GET    | `/children/{id}/status`      | Latest reading + status          |
| GET    | `/route`                     | Expected route + thresholds      |
| GET    | `/health`                    | Liveness                         |
| WS     | `/ws/alerts`                 | Live alert broadcast             |

Reading schema:

```json
{"child_id": "child-001", "gps_lat": -26.2475, "gps_lon": 27.8532,
 "hr": 92, "skin_distance_cm": 0.4, "battery": 96}
```

Trigger logic:

- `skin_off`: skin gap > 2.5 cm
- `off_route`: > 2 m off route for > 5 min
- `hr_spike_no_movement`: HR > 130 with < 2 m movement
- `possible_faint`: HR < 50 with < 2 m movement
- `early_departure`: movement before 06:00 local (override: `SAFESTEPS_EARLIEST_HOUR`)
- `possible_drowning`: depth > 100 cm + submerged > 30 s + < 1 m movement + HR > 130 (immediate)
- `water_watch` (not an alert): depth 20–80 cm with movement → watch-only until dry

## New features

- **Favorite routes + daily schedule** — `POST /routes` saves a named
  route (waypoints, destination, arrival/departure, supervisor contacts)
  and pre-populates the EMS cache (mock SAPS 10111 + nearby clinic);
  `GET /routes`, `POST /schedule`, `GET /schedule/{date}` manage the
  day plan. Persisted in `backend/routes.json`. The onboarding screen
  has “Save as Favorite” plus a Trip Mode toggle (min 2 supervisors).
- **Drowning detection** — the band is 12 h waterproof and streams
  `water_depth_cm` + `water_time_sec`. Simulator:
  `--mode pool_play` (40 cm, splashing) and `--mode drowning`
  (120 cm, 60 s still, HR 145).
- **EMS auto-escalation** — every alert gets an `id`. `POST
  /alerts/{id}/ack` acknowledges it; with no ack in 5 min
  (override: `SAFESTEPS_ACK_TIMEOUT_SECS`) the backend writes
  `backend/ems_call.json` (child name, parent, 5 contacts, age,
  location, nature, profile link) and broadcasts `ems_escalation`.
  Register the profile via `POST /children/{id}/profile`.

## Cost model (target < R300 per child)

- **Band BOM < R300**: BLE SoC + PPG heart-rate sensor + capacitive
  skin-contact pad + GPS (duty-cycled) in a breathable sock-band;
  NB-IoT module for areas without phone coverage.
- **NB-IoT**: one small packet per 2 s window (batched to ~1/min
  when calm, burst on alert) keeps data under a few MB/month —
  a ~R15/month pooled IoT SIM covers it.
- **Community mesh**: spaza shops and schools run solar BLE/NB-IoT
  relays so bands hop to the cloud even where coverage is thin;
  alerts fan out to 5 contacts + SMS fallback + 500 m community
  broadcast at near-zero marginal cost.
- **Backend**: single small VPS (or serverless) per district;
  AI summaries only on alert, not per ping.
