// Backend client with mock fallback (works even when backend is offline).
// On a physical phone, replace localhost with your PC's LAN IP, e.g.
// export const BACKEND_URL = 'http://192.168.1.20:8000';
export const BACKEND_URL = 'http://localhost:8000';

export const MOCK_STATUS = {
  child_id: 'child-001',
  status: 'ok',
  last: {
    child_id: 'child-001',
    gps_lat: -26.2475,
    gps_lon: 27.8532,
    hr: 92,
    skin_distance_cm: 0.4,
    battery: 96,
  },
  last_seen: new Date().toISOString(),
  off_route_m: 1.2,
  last_alert: null,
};

export const MOCK_ALERT = {
  anomaly: true,
  type: 'off_route',
  location: { gps_lat: -26.247, gps_lon: 27.856 },
  detail: '210m off route for 5.2min.',
  ai_summary: 'Child left the expected route near the Spaza turn and kept walking east. Highest risk: road crossing without supervision — call now.',
  actions: ['notify 5 contacts', 'SMS fallback', 'community alert 500m'],
  child_id: 'child-001',
  timestamp: new Date().toISOString(),
};

// Mock nearby help points (Soweto demo area) — replace with Places API later.
export const NEARBY_HELP = [
  { name: 'Orlando SAPS', kind: 'Police', phone: '+27118761010', dist_m: 640 },
  { name: 'Chiawelo Clinic', kind: 'Clinic', phone: '+27111301001', dist_m: 890 },
  { name: 'Protea Glen SAPS', kind: 'Police', phone: '+27118711014', dist_m: 1450 },
];

export async function fetchStatus(childId) {
  try {
    const res = await fetch(`${BACKEND_URL}/children/${childId}/status`);
    if (!res.ok) throw new Error('bad status ' + res.status);
    return { data: await res.json(), live: true };
  } catch (e) {
    return { data: MOCK_STATUS, live: false };
  }
}

async function postJSON(path, body) {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} -> ${res.status}`);
  return res.json();
}

async function getJSON(path) {
  const res = await fetch(`${BACKEND_URL}${path}`);
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return res.json();
}

// Favorite routes + daily schedule (persisted in backend/routes.json).
export const saveRoute = (route) => postJSON('/routes', route);
export const fetchRoutes = () => getJSON('/routes');
export const saveSchedule = (date, route_id) => postJSON('/schedule', { date, route_id });
export const fetchSchedule = (date) => getJSON(`/schedule/${date}`);

// Child profile feeds the EMS auto-escalation call sheet.
export const saveChildProfile = (childId, profile) =>
  postJSON(`/children/${childId}/profile`, profile);

// Ack an alert to stop the 5-minute EMS auto-escalation.
export const ackAlert = (alertId) => postJSON(`/alerts/${alertId}/ack`, {});
