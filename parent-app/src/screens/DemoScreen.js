import { useEffect, useState } from 'react';
import { ScrollView, View } from 'react-native';
import { demoScenarios, demoPlay, demoStatus, fetchRoute, DEFAULT_ROUTE } from '../api';
import { C, LINK_COLOR } from '../theme';
import { T, Btn, Card, Chip } from '../ui';
import { Triage } from './AlertScreen';

const KIND_COLOR = { start: C.blue, scenario: C.text, link: C.blue, band: C.orange, alert: C.red, note: C.amber, done: C.green, error: C.red };

const PIPELINE = [
  ['Band (simulated)', 'Skin, heart-rate, Global Positioning System (GPS) and water sensors. Runs the safety rules on the band itself and buffers readings when offline.'],
  ['Closest link', 'Direct, a nearby relay, or Short Message Service (SMS). With no link at all the band still buzzes and stores readings.'],
  ['Rule engine (backend)', 'Raises the alert instantly. It never waits for AI.'],
  ['Meta Model triage', 'muse-wonder-1.0 reads the alert, calls tools for history and context, and returns severity, reasons and a message in the parent’s language. It cannot cancel or delay an alert.'],
  ['Parent app', 'Live alert, acknowledge, call. If nobody acknowledges within 5 minutes, Emergency Medical Services (EMS) escalation starts.'],
];

const STATUS = [
  ['Rule engine, alerts, live push, acknowledge', 'BUILT', C.green],
  ['Meta Model triage with tool calls', 'BUILT', C.green],
  ['Offline buffering and relay flush', 'BUILT', C.green],
  ['Saved logs round coordinates to about 100 m', 'BUILT', C.green],
  ['Personal baseline: Meta Model proposes, server limits, parent approves', 'BUILT', C.green],
  ['Baseline learned from real trips (the demo history is synthetic)', 'ROADMAP', C.mute],
  ['Automated tests for the rule engine, baseline and AI client', 'BUILT', C.green],
  ['Shared access PIN on every data endpoint', 'BUILT', C.green],
  ['Phone as the band: real GPS, simulated sensors', 'BUILT', C.green],
  ['Band hardware, heart-rate and skin sensors', 'SIMULATED', C.amber],
  ['User accounts and encryption at rest', 'ROADMAP', C.mute],
  ['SMS fallback (message printed, no gateway)', 'SIMULATED', C.amber],
  ['EMS call (written to a file, no real call)', 'SIMULATED', C.amber],
  ['Route map (offline drawing, no map tiles)', 'SIMPLE', C.amber],
  ['500 m community mesh alert', 'ROADMAP', C.mute],
  ['20 s audio and video bursts', 'ROADMAP', C.mute],
  ['Full Protection of Personal Information Act (POPIA) review', 'ROADMAP', C.mute],
];

function Label({ children }) {
  return <T style={{ color: C.mute, fontSize: 11, letterSpacing: 0.8, marginBottom: 6 }}>{String(children).toUpperCase()}</T>;
}

export default function DemoScreen({ alert, aiStat, ws, onOpenAlert }) {
  const [scenarios, setScenarios] = useState([]);
  const [run, setRun] = useState({ running: false, scenario: null, log: [] });
  const [route, setRoute] = useState(DEFAULT_ROUTE);
  const [err, setErr] = useState('');

  useEffect(() => {
    demoScenarios().then((d) => setScenarios(d.scenarios)).catch(() => setErr('Backend not reachable. Start it, then reload.'));
    fetchRoute().then(setRoute);
    let alive = true;
    const tick = async () => {
      try { const s = await demoStatus(); if (alive) setRun(s); } catch (e) { /* offline */ }
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const play = async (id) => {
    setErr('');
    try { await demoPlay(id); } catch (e) { setErr(String(e.message || e).includes('409') ? 'A demo is already running.' : 'Could not start the demo.'); }
  };

  const rules = [
    ['Band off skin', 'gap above 2.5 cm'],
    ['Heart-rate spike', 'above 130 bpm and still (under 2 m)'],
    ['Possible faint', 'below 50 bpm and still'],
    ['Possible drowning', 'deeper than 100 cm for over 30 s, heart rate above 130, no movement'],
    ['Off route', `over ${route.off_route_dist_m} m from the route for ${Math.round((route.off_route_secs || 300) / 60)} min`],
    ['Early departure', 'movement before 06:00'],
  ];

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 14 }}>
      <View>
        <T head style={{ fontSize: 28 }}>Live demo</T>
        <T style={{ color: C.mute, marginTop: 2 }}>
          Runs inside the backend, no terminal needed. Rules, alerts, live push and Meta Model triage are real; the band is simulated.
        </T>
      </View>

      {err ? <T style={{ color: C.amber }}>{err}</T> : null}

      <View style={{ gap: 10 }}>
        {scenarios.map((s) => (
          <Card key={s.id} style={{ gap: 8 }}>
            <T head style={{ fontSize: 18 }}>{s.title}</T>
            <T style={{ color: C.mute, fontSize: 13 }}>{s.blurb}</T>
            <Btn small title={run.running && run.scenario === s.id ? 'Running…' : 'Play demo'} disabled={run.running} onPress={() => play(s.id)} />
          </Card>
        ))}
      </View>

      <Card>
        <Label>Live log</Label>
        {run.log.length === 0 ? <T style={{ color: C.mute }}>Press “Play demo”. Steps appear here as they happen.</T> : null}
        {run.log.slice(-16).map((e, i) => (
          <T key={i} mono style={{ color: KIND_COLOR[e.kind] || C.text, fontSize: 12, marginBottom: 2 }}>
            [{e.kind}] {e.msg}
          </T>
        ))}
      </Card>

      <Card style={{ gap: 8 }}>
        <Label>Latest alert</Label>
        {alert ? (
          <View style={{ gap: 8 }}>
            <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <T head style={{ fontSize: 20, color: C.red }}>{alert.type.replace(/_/g, ' ').toUpperCase()}</T>
              {alert.link && alert.link !== 'direct' ? <Chip label={`VIA ${alert.link.toUpperCase()}`} color={LINK_COLOR[alert.link] || C.mute} /> : null}
            </View>
            <T style={{ color: C.mute }}>{alert.detail}</T>
            <Triage a={alert} />
            <Btn small kind="ghost" title="Open full alert screen" onPress={onOpenAlert} />
          </View>
        ) : <T style={{ color: C.mute }}>No alert yet.</T>}
      </Card>

      <Card>
        <Label>Meta Model usage</Label>
        {aiStat && aiStat.configured ? (
          <View style={{ gap: 2 }}>
            <T mono style={{ fontSize: 12 }}>model {aiStat.model}</T>
            <T mono style={{ fontSize: 12 }}>calls {aiStat.calls} · retries {aiStat.retries ?? 0} · errors {aiStat.errors}</T>
            <T mono style={{ fontSize: 12 }}>tokens in {aiStat.prompt_tokens} · out {aiStat.completion_tokens}</T>
            <T mono style={{ fontSize: 12 }}>estimated cost ${aiStat.est_cost_usd} (estimate; see the Meta Usage page)</T>
            {aiStat.last_error ? <T mono style={{ fontSize: 12, color: C.amber }}>last error: {aiStat.last_error}</T> : null}
          </View>
        ) : <T style={{ color: C.mute }}>{aiStat ? 'No Meta key set on the backend. Rule-based alerts only.' : 'Backend unreachable.'}</T>}
        <T style={{ color: C.mute, fontSize: 12, marginTop: 6 }}>Live connection: {ws}</T>
      </Card>

      <Card style={{ gap: 8 }}>
        <Label>How it works</Label>
        {PIPELINE.map(([t, d], i) => (
          <View key={t} style={{ flexDirection: 'row', gap: 10 }}>
            <T head style={{ color: C.orange, fontSize: 20, width: 22 }}>{i + 1}</T>
            <View style={{ flex: 1 }}>
              <T style={{ fontWeight: '700' }}>{t}</T>
              <T style={{ color: C.mute, fontSize: 13 }}>{d}</T>
            </View>
          </View>
        ))}
      </Card>

      <Card style={{ gap: 6 }}>
        <Label>Rule engine</Label>
        {rules.map(([r, d]) => (
          <View key={r} style={{ flexDirection: 'row', gap: 10 }}>
            <T style={{ fontWeight: '700', width: 120 }}>{r}</T>
            <T style={{ color: C.mute, flex: 1, fontSize: 13 }}>{d}</T>
          </View>
        ))}
      </Card>

      <Card style={{ gap: 8 }}>
        <Label>Honest status</Label>
        {STATUS.map(([t, tag, color]) => (
          <View key={t} style={{ flexDirection: 'row', gap: 10, alignItems: 'center', justifyContent: 'space-between' }}>
            <T style={{ flex: 1, fontSize: 13 }}>{t}</T>
            <Chip label={tag} color={color} />
          </View>
        ))}
      </Card>
    </ScrollView>
  );
}
