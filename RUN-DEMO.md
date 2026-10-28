# SafeSteps demo - run guide (Windows PowerShell)

One-time:
  winget install --id Cloudflare.cloudflared
  cd parent-app; npm install; npx expo export --platform web; cd ..      # rebuilds parent-app\dist
  .venv\Scripts\activate; pip install -r backend\requirements.txt

Terminal 1 - backend (serves the app AND the API on port 8000):
  $env:META_API_KEY="<your key>"          # never commit or screenshot this
  uvicorn backend.main:app --host 0.0.0.0 --port 8000
  # prove the Meta Model API works:  curl.exe -X POST http://localhost:8000/ai/selftest

Terminal 2 - public link (works on any network, phone on mobile data too):
  cloudflared tunnel --url http://localhost:8000
  # open the https://....trycloudflare.com URL on your phone
  # if it cannot connect, retry with:  cloudflared tunnel --protocol http2 --url http://localhost:8000

Terminal 3 - the band (offline demo):
  python band-simulator\simulate.py --mode demo --fast 20 --link-plan "direct:15,offline:40,relay:20,direct"

Env knobs: META_API_BASE (default https://api.meta.ai/v1), META_MODEL (default muse-wonder-1.0),
SAFESTEPS_ALERT_COOLDOWN_SECS (default 60).
