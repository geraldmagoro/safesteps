import { useState } from 'react';
import { View, Text, Button, StyleSheet, ScrollView, Linking } from 'react-native';
import { MOCK_ALERT, NEARBY_HELP, ackAlert } from '../api';

// Alert screen: map + AI summary + Call All + nearby SAPS/clinics +
// 20 s audio/video burst player placeholders.
export default function AlertScreen({ profile, alert, onBack }) {
  const a = alert || MOCK_ALERT;
  const [acked, setAcked] = useState(false);
  const ai = a.ai || {};
  const sevColor = { critical: '#b00', high: '#d60', medium: '#a80', low: '#080' }[ai.severity] || '#555';

  const ack = async () => {
    try { await ackAlert(a.id); setAcked(true); } catch (e) { setAcked('error'); }
  };

  const callAll = () => {
    // MVP: dial the first contact; v2 loops all 5 with SMS fallback.
    const first = profile.contacts[0].replace(/\s/g, '');
    Linking.openURL(`tel:${first}`);
  };

  return (
    <ScrollView contentContainerStyle={styles.wrap}>
      <Text style={styles.title}>⚠ {a.type.replace(/_/g, ' ').toUpperCase()}</Text>
      <Text>{a.detail}</Text>

      <View style={styles.mapBox}>
        <Text style={styles.mapText}>
          {a.location.gps_lat.toFixed(5)}, {a.location.gps_lon.toFixed(5)}
        </Text>
      </View>

      {a.link && a.link !== 'direct' ? (
        <Text style={styles.hint}>Delivered via {a.link}
          {a.delivery_delay_s ? ` (${a.delivery_delay_s}s after the band detected it)` : ''}
          {a.edge_alarm ? ' - band buzzer already sounded' : ''}</Text>
      ) : null}

      <Text style={styles.label}>AI triage</Text>
      {ai.status === 'pending' ? <Text style={styles.hint}>Meta Model analysing... (alert already sent)</Text> : null}
      {ai.status === 'error' ? <Text style={styles.hint}>AI unavailable ({ai.error}). Rule-based alert stands.</Text> : null}
      {ai.status === 'ok' ? (
        <View>
          <Text style={{ color: sevColor, fontWeight: '700' }}>
            Severity: {String(ai.severity).toUpperCase()} - confidence {Math.round((ai.confidence || 0) * 100)}%
            {ai.likely_false_alarm ? ' - may be a false alarm (still check)' : ''}
          </Text>
          {(ai.reasons || []).map((r, i) => <Text key={i}>- {r}</Text>)}
          {ai.parent_message_local ? <Text style={styles.summary}>{ai.parent_message_local}</Text> : null}
          <Text style={styles.hint}>Model: {ai.model}</Text>
        </View>
      ) : null}
      <Text style={styles.summary}>{a.ai_summary}</Text>

      <Text style={styles.label}>Actions</Text>
      {a.actions.map((x) => (
        <Text key={x}>• {x}</Text>
      ))}

      <View style={styles.gap} />
      {a.id ? (
        <Button title={acked === true ? 'Acknowledged - EMS escalation stopped' : acked === 'error' ? 'Ack failed - retry' : 'I SEE THIS (acknowledge)'}
          color="#070" onPress={ack} />
      ) : null}
      <View style={styles.gap} />
      <Button title="CALL ALL (5 contacts)" color="#b00" onPress={callAll} />

      <Text style={styles.label}>20 s bursts</Text>
      <View style={styles.row}>
        <Button title="▶ Audio burst" onPress={() => {}} />
        <Button title="▶ Video burst" onPress={() => {}} />
      </View>
      <Text style={styles.hint}>(Placeholders in MVP — clips attach here.)</Text>

      <Text style={styles.label}>Nearby help</Text>
      {NEARBY_HELP.map((h) => (
        <View key={h.name} style={styles.helpRow}>
          <Text>{h.kind}: {h.name} ({h.dist_m}m)</Text>
          <Button title="Call" onPress={() => Linking.openURL(`tel:${h.phone}`)} />
        </View>
      ))}

      <View style={styles.gap} />
      <Button title="Back to live map" onPress={onBack} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 20, gap: 6 },
  title: { fontSize: 22, fontWeight: 'bold', color: '#b00' },
  mapBox: { borderWidth: 1, borderColor: '#333', borderRadius: 8, padding: 20,
    alignItems: 'center', marginVertical: 8, backgroundColor: '#fde' },
  mapText: { fontSize: 18, fontWeight: 'bold' },
  label: { fontWeight: '700', marginTop: 10 },
  summary: { fontStyle: 'italic' },
  row: { flexDirection: 'row', gap: 10, marginTop: 4 },
  hint: { color: '#666', fontSize: 12 },
  helpRow: { flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', marginTop: 4 },
  gap: { height: 10 },
});
