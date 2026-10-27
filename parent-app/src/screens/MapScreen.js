import { useEffect, useState } from 'react';
import { View, Text, Button, StyleSheet } from 'react-native';
import { fetchStatus } from '../api';

// Live map screen. MVP renders coordinates + vitals (no map SDK needed);
// swap the placeholder box for react-native-maps MapView in v2.
export default function MapScreen({ profile, onAlert }) {
  const [status, setStatus] = useState(null);
  const [live, setLive] = useState(false);

  const refresh = async () => {
    const { data, live } = await fetchStatus(profile.childId);
    setStatus(data);
    setLive(live);
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);

  const last = status?.last;

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>Live: {profile.childName}</Text>
      <Text style={live ? styles.live : styles.mock}>
        {live ? '● LIVE from backend' : '○ MOCK data (backend offline)'}
      </Text>

      <View style={styles.mapBox}>
        <Text style={styles.mapText}>
          {last ? `${last.gps_lat.toFixed(5)}, ${last.gps_lon.toFixed(5)}` : 'waiting for GPS…'}
        </Text>
        <Text>Home → Spaza (left) → School</Text>
      </View>

      {last && (
        <View style={styles.vitals}>
          <Text>HR: {last.hr} bpm</Text>
          <Text>Skin gap: {last.skin_distance_cm} cm</Text>
          <Text>Battery: {last.battery}%</Text>
          <Text>Off-route: {status.off_route_m ?? '?'} m</Text>
          <Text>Status: {status.status}</Text>
        </View>
      )}

      <Button title="Refresh" onPress={refresh} />
      <View style={styles.gap} />
      <Button title="Open latest alert (demo)" color="#b00" onPress={onAlert} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 20, gap: 8, flex: 1 },
  title: { fontSize: 22, fontWeight: 'bold' },
  live: { color: 'green', fontWeight: '600' },
  mock: { color: '#a60', fontWeight: '600' },
  mapBox: { borderWidth: 1, borderColor: '#333', borderRadius: 8, padding: 24,
    alignItems: 'center', marginVertical: 10, backgroundColor: '#eef4ee' },
  mapText: { fontSize: 18, fontWeight: 'bold' },
  vitals: { gap: 2, marginBottom: 10 },
  gap: { height: 8 },
});
