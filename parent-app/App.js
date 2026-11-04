import { useCallback, useEffect, useRef, useState } from 'react';
import { SafeAreaView, View, Image, Pressable } from 'react-native';
import OnboardingScreen from './src/screens/OnboardingScreen';
import MapScreen from './src/screens/MapScreen';
import AlertScreen from './src/screens/AlertScreen';
import DemoScreen from './src/screens/DemoScreen';
import BaselineScreen from './src/screens/BaselineScreen';
import { wsUrl, saveChildProfile, saveRoute, fetchAIStatus, authCheck, setPin } from './src/api';
import { C } from './src/theme';
import { T, Btn, Input } from './src/ui';

const DEMO_PROFILE = {
  childName: 'Naledi', school: 'Orlando East Primary', route: 'Home -> Spaza (left) -> School',
  // Labelled placeholders, never real numbers: demo mode must not dial anyone.
  contacts: ['Mother (demo)', 'Father (demo)', 'Gogo (demo)', 'Neighbour (demo)', 'Teacher (demo)'],
  photo: null, language: 'isiZulu', childId: 'child-001', favoriteRoute: 'School run',
  tripMode: false, supervisors: [], demo: true,
};

function PinScreen({ onUnlock }) {
  const [v, setV] = useState('');
  const [err, setErr] = useState('');
  const go = async () => {
    setPin(v.trim());
    const r = await authCheck();
    if (r.ok) onUnlock(); else setErr('Wrong PIN. Try again.');
  };
  return (
    <View style={{ padding: 20, gap: 12 }}>
      <T head style={{ fontSize: 24 }}>Enter access PIN</T>
      <T style={{ color: C.mute }}>This demo is protected, because it shows a child’s location.</T>
      <Input value={v} onChangeText={setV} placeholder="PIN" secureTextEntry keyboardType="numeric" />
      {err ? <T style={{ color: C.red }}>{err}</T> : null}
      <Btn title="Unlock" onPress={go} />
    </View>
  );
}

function Tab({ label, active, onPress }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button"
      style={{ paddingVertical: 8, paddingHorizontal: 16, borderRadius: 99, borderWidth: 1,
        borderColor: active ? C.orange : C.line, backgroundColor: active ? C.orange : 'transparent' }}>
      <T style={{ color: active ? '#1A1308' : C.text, fontWeight: '700', fontSize: 13 }}>{label}</T>
    </Pressable>
  );
}

export default function App() {
  const [profile, setProfile] = useState(null);
  const [tab, setTab] = useState('parent');
  const [screen, setScreen] = useState('map');
  const [alert, setAlert] = useState(null);
  const [ws, setWs] = useState('connecting');
  const [ems, setEms] = useState(null);
  const [aiStat, setAiStat] = useState(null);
  const [authDone, setAuthDone] = useState(false);
  const [needPin, setNeedPin] = useState(false);
  const alertRef = useRef(null);
  const tabRef = useRef('parent');
  const profileRef = useRef(null);
  alertRef.current = alert;
  tabRef.current = tab;
  profileRef.current = profile;

  const onDone = useCallback(async (p) => {
    setProfile(p);
    try {
      await saveChildProfile(p.childId, {
        full_name: p.childName, contacts: p.contacts, school: p.school, language: p.language || '',
      });
      if (p.favoriteRoute) await saveRoute({ name: p.favoriteRoute, destination: p.school, supervisor_contacts: p.supervisors });
    } catch (e) { /* backend offline: app keeps working with mock data */ }
  }, []);

  useEffect(() => {
    authCheck().then((a) => { setNeedPin(!!a.pin_required && !a.ok); setAuthDone(true); });
  }, []);

  // Live push over WebSocket with auto-reconnect (works before and after setup).
  useEffect(() => {
    if (!authDone || needPin) return undefined;
    let sock; let timer; let closed = false;
    const connect = () => {
      try { sock = new WebSocket(wsUrl()); } catch (e) { timer = setTimeout(connect, 3000); return; }
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
          setAlert(m);
          if (tabRef.current === 'parent' && profileRef.current) setScreen('alert');
        }
      };
    };
    connect();
    return () => { closed = true; clearTimeout(timer); if (sock) sock.close(); };
  }, [authDone, needPin]);

  useEffect(() => {
    if (!authDone || needPin) return undefined;
    const tick = async () => setAiStat(await fetchAIStatus());
    tick();
    const t = setInterval(tick, 6000);
    return () => clearInterval(t);
  }, [authDone, needPin]);

  const aiLine = aiStat
    ? (aiStat.configured ? `Meta ${aiStat.model} · ${aiStat.calls} calls · ~$${aiStat.est_cost_usd}` : 'AI: no key set')
    : 'AI: backend unreachable';

  let body;
  if (needPin) {
    body = <PinScreen onUnlock={() => setNeedPin(false)} />;
  } else if (tab === 'baseline') {
    body = <BaselineScreen />;
  } else if (tab === 'demo') {
    body = <DemoScreen alert={alert} aiStat={aiStat} ws={ws}
      onOpenAlert={() => { setTab('parent'); if (profile) setScreen('alert'); }} />;
  } else if (!profile) {
    body = (
      <View style={{ flex: 1 }}>
        <View style={{ padding: 12, paddingBottom: 0 }}>
          <Btn kind="ghost" title="Skip setup: load demo profile (Naledi)" onPress={() => onDone(DEMO_PROFILE)} />
        </View>
        <OnboardingScreen onDone={onDone} />
      </View>
    );
  } else if (screen === 'alert') {
    body = <AlertScreen profile={profile} alert={alert} onBack={() => setScreen('map')} />;
  } else {
    body = <MapScreen profile={profile} hasAlert={!!alert} onAlert={() => setScreen('alert')} />;
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: C.bg }}>
      <View style={{ paddingHorizontal: 16, paddingTop: 12, paddingBottom: 10, borderBottomWidth: 1, borderBottomColor: C.line, gap: 10 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Image source={require('./assets/logo.png')} style={{ width: 38, height: 38 }} resizeMode="contain" />
          <View style={{ flex: 1 }}>
            <T head style={{ fontSize: 22, lineHeight: 24 }}>SafeSteps</T>
            <T style={{ color: C.mute, fontSize: 12 }}>Ankle-band safety for the walk to school</T>
          </View>
        </View>
        <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <Tab label="Parent" active={tab === 'parent'} onPress={() => setTab('parent')} />
          <Tab label="Live demo" active={tab === 'demo'} onPress={() => setTab('demo')} />
          <Tab label="Baseline" active={tab === 'baseline'} onPress={() => setTab('baseline')} />
          <View style={{ flex: 1, minWidth: 120 }}>
            <T mono style={{ color: ws === 'live' ? C.green : C.amber, fontSize: 11 }}>● alerts {ws}</T>
            <T mono style={{ color: C.mute, fontSize: 11 }}>{aiLine}</T>
          </View>
        </View>
      </View>
      {ems ? (
        <View style={{ backgroundColor: C.red, padding: 8 }}>
          <T style={{ color: '#fff', fontWeight: '700' }}>EMS ESCALATION SENT for {ems.child_full_name}: {ems.nature}</T>
        </View>
      ) : null}
      <View style={{ flex: 1 }}>{body}</View>
    </SafeAreaView>
  );
}
