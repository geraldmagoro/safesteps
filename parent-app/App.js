import { useCallback, useEffect, useRef, useState } from 'react';
import { SafeAreaView, View, Text, Button, StyleSheet } from 'react-native';
import OnboardingScreen from './src/screens/OnboardingScreen';
import MapScreen from './src/screens/MapScreen';
import AlertScreen from './src/screens/AlertScreen';
import { WS_URL, BACKEND_URL, saveChildProfile, saveRoute, fetchAIStatus } from './src/api';

const DEMO_PROFILE = {
  childName: 'Naledi', school: 'Orlando East Primary', route: 'Home -> Spaza (left) -> School',
  contacts: ['+27820000001', '+27820000002', '+27820000003', '+27820000004', '+27820000005'],
  photo: null, language: 'isiZulu', childId: 'child-001', favoriteRoute: 'School run',
  tripMode: false, supervisors: [],
};

export default function App() {
  const [profile, setProfile] = useState(null);
  const [screen, setScreen] = useState('map');
  const [alert, setAlert] = useState(null);
  const [ws, setWs] = useState('connecting');
  const [ems, setEms] = useState(null);
  const [aiStat, setAiStat] = useState(null);
  const alertRef = useRef(null);
  alertRef.current = alert;

  const onDone = useCallback(async (p) => {
    setProfile(p);
    try {
      await saveChildProfile(p.childId, {
        full_name: p.childName, contacts: p.contacts, school: p.school, language: p.language || '',
      });
      if (p.favoriteRoute) await saveRoute({ name: p.favoriteRoute, destination: p.school, supervisor_contacts: p.supervisors });
    } catch (e) { /* backend offline: app keeps working with mock data */ }
  }, []);

  // Live alerts over WebSocket, with auto-reconnect.
  useEffect(() => {
    if (!profile) return undefined;
    let sock; let timer; let closed = false;
    const connect = () => {
      try { sock = new WebSocket(WS_URL); } catch (e) { timer = setTimeout(connect, 3000); return; }
      sock.onopen = () => setWs('live');
      sock.onclose = () => { setWs('reconnecting'); if (!closed) timer = setTimeout(connect, 3000); };
      sock.onerror = () => {};
      sock.onmessage = (ev) => {
        let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
        if (m.event === 'alert_update') {
          if (alertRef.current && alertRef.current.id === m.id) {
            setAlert({ ...alertRef.current, ai: m.ai, ai_summary: m.ai_summary });
          }
        } else if (m.type === 'ems_escalation') {
          setEms(m);
        } else if (m.anomaly) {
          setAlert(m); setScreen('alert');
        }
      };
    };
    connect();
    return () => { closed = true; clearTimeout(timer); if (sock) sock.close(); };
  }, [profile]);

  // Meta Model API usage chip.
  useEffect(() => {
    if (!profile) return undefined;
    const tick = async () => setAiStat(await fetchAIStatus());
    tick();
    const t = setInterval(tick, 8000);
    return () => clearInterval(t);
  }, [profile]);

  if (!profile) {
    return (
      <SafeAreaView style={styles.root}>
        <View style={styles.demoBar}>
          <Button title="Skip setup: load demo profile (Naledi)" onPress={() => onDone(DEMO_PROFILE)} />
        </View>
        <OnboardingScreen onDone={onDone} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.root}>
      <View style={styles.bar}>
        <Text style={styles.barText}>Alerts: {ws}</Text>
        <Text style={styles.barText}>
          {aiStat ? (aiStat.configured
            ? `Meta ${aiStat.model}: ${aiStat.calls} calls, ~$${aiStat.est_cost_usd} est.${aiStat.last_error ? ' (last call failed)' : ''}`
            : 'AI: no key set (rule-based only)') : 'AI: backend unreachable'}
        </Text>
      </View>
      {ems ? (
        <View style={styles.ems}>
          <Text style={styles.emsText}>EMS ESCALATION SENT for {ems.child_full_name}: {ems.nature}</Text>
        </View>
      ) : null}
      {screen === 'alert' ? (
        <AlertScreen profile={profile} alert={alert} onBack={() => setScreen('map')} />
      ) : (
        <MapScreen profile={profile} onAlert={() => { if (!alert) setAlert(null); setScreen('alert'); }} />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#fff' },
  demoBar: { padding: 8, backgroundColor: '#eef' },
  bar: { padding: 6, backgroundColor: '#112', gap: 2 },
  barText: { color: '#cfe', fontSize: 12 },
  ems: { backgroundColor: '#b00', padding: 8 },
  emsText: { color: '#fff', fontWeight: '700' },
});
