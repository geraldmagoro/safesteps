# SafeSteps demo - run guide (Windows PowerShell)

One-time setup:
  .\.venv\Scripts\Activate.ps1
  pip install -r backend\requirements.txt
  cd parent-app; npm install; npx expo export --platform web; cd ..     # rebuilds parent-app\dist

Terminal 1 - backend (serves the app AND the API on port 8000):
  $env:META_API_KEY="<your key>"          # never commit or screenshot this
  $env:SAFESTEPS_PIN="<a PIN>"            # optional, recommended whenever the link is public
  uvicorn backend.main:app --host 0.0.0.0 --port 8000
  # prove the Meta Model API works (add -H "x-pin: <PIN>" if a PIN is set):
  curl.exe -X POST http://localhost:8000/ai/selftest

Open http://localhost:8000
  1. Parent tab -> "Skip setup: load demo profile" (saves the isiZulu profile).
  2. "Live demo" tab -> "Play demo". The alert appears, then Meta Model triage fills in.

Baseline tab (personal baseline):
  Load synthetic history -> Analyse with Meta Model -> Approve -> Play "runner at the crossing" (before and after).

Phone as the band (real GPS):
  Terminal 2:  cloudflared tunnel --url http://localhost:8000
               (if it cannot connect: cloudflared tunnel --protocol http2 --url http://localhost:8000)
  On the phone open  https://<the-tunnel-address>/band   (https is required for GPS)
  Enter the PIN if asked, press "Start band", then "Set HOME here", walk 20 m+, "Set SCHOOL here".
  Use the buttons for band off, heart rate, child stopped, and Direct / Relay / Offline.
  Open the same tunnel address on the laptop to watch the parent app.

Band simulator (optional):
  python band-simulator\simulate.py --mode spike --fast 5 --link-plan "direct:3,offline:20,relay:10,direct"
  (add --pin <PIN> if a PIN is set)

Tests:
  pip install -r requirements-dev.txt
  pytest

Env knobs: META_API_BASE (default https://api.meta.ai/v1), META_MODEL (default muse-wonder-1.0),
META_API_RETRIES (6), SAFESTEPS_ALERT_COOLDOWN_SECS (60), SAFESTEPS_OFF_ROUTE_M (15), SAFESTEPS_PIN.

Network note: if the AI step shows "getaddrinfo failed", the local DNS is flaky; the backend retries
automatically. A phone hotspot is the backup.
