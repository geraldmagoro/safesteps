import { useEffect, useState } from 'react';
import { View, ScrollView, Linking } from 'react-native';
import { MOCK_ALERT, NEARBY_HELP, ackAlert, DEFAULT_ROUTE, fetchRoute } from '../api';
import { C, LINK_COLOR } from '../theme';
import { T, Btn, Card, Chip } from '../ui';
import RouteMap from '../RouteMap';

export const SEV_COLOR = { critical: C.red, high: C.orange, medium: C.amber, low: C.green };

// Compact AI triage block, shared with the Demo screen.
export function Triage({ a }) {
  const ai = a.ai || {};
  return (
    <View style={{ gap: 4 }}>
      {ai.status === 'pending' && <T style={{ color: C.blue }}>Meta Model analysing… the alert has already been sent.</T>}
      {ai.status === 'error' && <T style={{ color: C.amber }}>AI unavailable ({ai.error}). The rule-based alert stands.</T>}
      {ai.status === 'offline' && <T style={{ color: C.mute }}>AI not configured. Rule-based alert only.</T>}
      {ai.status === 'ok' && (
        <View style={{ gap: 3 }}>
          <T style={{ color: SEV_COLOR[ai.severity] || C.text, fontWeight: '700' }}>
            Severity {String(ai.severity).toUpperCase()} · confidence {Math.round((ai.confidence || 0) * 100)}%
            {ai.likely_false_alarm ? ' · may be a false alarm (still check)' : ''}
          </T>
          {(ai.reasons || []).map((r, i) => <T key={i} style={{ color: C.mute }}>· {r}</T>)}
          <T style={{ fontStyle: 'italic', marginTop: 4 }}>{ai.parent_message || a.ai_summary}</T>
          {ai.parent_message_local ? <T style={{ fontStyle: 'italic', color: C.orange }}>{ai.parent_message_local}</T> : null}
          <T mono style={{ color: C.mute, fontSize: 11 }}>model: {ai.model}</T>
        </View>
      )}
      {!ai.status && <T style={{ fontStyle: 'italic' }}>{a.ai_summary}</T>}
    </View>
  );
}

// Alert screen: map + AI triage + acknowledge + Call All + nearby help.
export default function AlertScreen({ profile, alert, onBack }) {
  const a = alert || MOCK_ALERT;
  const [acked, setAcked] = useState(false);
  const [route, setRoute] = useState(DEFAULT_ROUTE);
  const [note, setNote] = useState('');
  useEffect(() => { fetchRoute().then(setRoute); }, []);
  const loc = [a.location.gps_lat, a.location.gps_lon];

  const ack = async () => {
    try { await ackAlert(a.id); setAcked(true); } catch (e) { setAcked('error'); }
  };
  const callAll = () => {
    // MVP: dial the first contact; v2 loops all 5 with SMS fallback.
    if (profile.demo) { setNote('Demo mode: nobody is dialled. In real use this calls your first contact.'); return; }
    const first = profile.contacts[0].replace(/\s/g, '');
    Linking.openURL(`tel:${first}`);
  };
  const callHelp = (h) => {
    // The list is sample data and may not be real numbers: never dial from it in the demo.
    setNote(`Demo mode: would call ${h.name}. Numbers in this list are sample data.`);
  };

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
      <View>
        <T head style={{ fontSize: 28, color: C.red }}>⚠ {a.type.replace(/_/g, ' ').toUpperCase()}</T>
        <T style={{ color: C.mute, marginTop: 2 }}>{a.detail}</T>
      </View>

      <RouteMap route={route} last={{ gps_lat: loc[0], gps_lon: loc[1] }} alertLoc={loc} offRouteM={999} />
      <T mono style={{ color: C.mute, fontSize: 12 }}>{loc[0].toFixed(5)}, {loc[1].toFixed(5)}</T>

      {a.link && a.link !== 'direct' && (
        <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <Chip label={`VIA ${a.link.toUpperCase()}`} color={LINK_COLOR[a.link] || C.mute} />
          {a.delivery_delay_s ? <T style={{ color: C.mute, fontSize: 12 }}>{a.delivery_delay_s}s after the band detected it</T> : null}
          {a.edge_alarm ? <T style={{ color: C.orange, fontSize: 12 }}>band buzzer already sounded</T> : null}
        </View>
      )}

      <Card>
        <T style={{ color: C.mute, fontSize: 11, letterSpacing: 0.8, marginBottom: 6 }}>AI TRIAGE</T>
        <Triage a={a} />
      </Card>

      <Card>
        <T style={{ color: C.mute, fontSize: 11, letterSpacing: 0.8, marginBottom: 6 }}>ACTIONS</T>
        {a.actions.map((x) => <T key={x}>• {x}</T>)}
      </Card>

      <View style={{ gap: 8 }}>
        {a.id ? (
          <Btn kind="ok" onPress={ack}
            title={acked === true ? 'Acknowledged · EMS escalation stopped' : acked === 'error' ? 'Ack failed · retry' : 'I SEE THIS (acknowledge)'} />
        ) : null}
        <Btn kind="danger" title="CALL FIRST CONTACT" onPress={callAll} />
        {note ? <T style={{ color: C.amber, fontSize: 12 }}>{note}</T> : null}
      </View>

      <Card>
        <T style={{ color: C.mute, fontSize: 11, letterSpacing: 0.8, marginBottom: 6 }}>20 S AUDIO / VIDEO BURSTS</T>
        <T style={{ color: C.mute, fontSize: 12 }}>Roadmap: band clips attach here. Not built in this MVP.</T>
      </Card>

      <Card style={{ gap: 8 }}>
        <T style={{ color: C.mute, fontSize: 11, letterSpacing: 0.8 }}>NEARBY HELP · SAMPLE LIST FOR THE DEMO</T>
        {NEARBY_HELP.map((h) => (
          <View key={h.name} style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <T>{h.kind}: {h.name} ({h.dist_m} m)</T>
            <Btn small kind="ghost" title="Call (demo)" onPress={() => callHelp(h)} />
          </View>
        ))}
      </Card>

      <Btn kind="ghost" title="Back to live map" onPress={onBack} />
    </ScrollView>
  );
}
