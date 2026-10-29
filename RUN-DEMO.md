# SafeSteps demo - run guide (Windows PowerShell)

One-time setup:
  .\.venv\Scripts\Activate.ps1
  pip install -r backend\requirements.txt
  cd parent-app; npm install; npx expo export --platform web; cd ..     # rebuilds parent-app\dist

Terminal 1 - backend (serves the app AND the API on port 8000):
  $env:META_API_KEY="<your key>"          # never commit or screenshot this
  uvicorn backend.main:app --host 0.0.0.0 --port 8000
  # prove the Meta Model API works:  curl.exe -X POST http://localhost:8000/ai/selftest

Open http://localhost:8000
  1. Parent tab -> "Skip setup: load demo profile" (saves the isiZulu profile).
  2. "Live demo" tab -> "Play demo". No terminal needed. The alert appears, then Meta Model triage fills in.

Public link for a phone (optional, works on any network):
  cloudflared tunnel --url http://localhost:8000
  # if it cannot connect: cloudflared tunnel --protocol http2 --url http://localhost:8000

Band simulator (optional, same backend):
  python band-simulator\simulate.py --mode spike --fast 5 --link-plan "direct:3,offline:20,relay:10,direct"

Env knobs: META_API_BASE (default https://api.meta.ai/v1), META_MODEL (default muse-wonder-1.0),
META_API_RETRIES (default 6), SAFESTEPS_ALERT_COOLDOWN_SECS (default 60),
SAFESTEPS_OFF_ROUTE_M (default 15).

Network note: if the AI step shows "getaddrinfo failed", the local DNS is flaky; the backend retries
automatically. A phone hotspot is the backup.
