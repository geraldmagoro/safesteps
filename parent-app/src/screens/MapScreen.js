import { useEffect, useState } from 'react';
import { ScrollView, View } from 'react-native';
import { fetchStatus, fetchRoute, DEFAULT_ROUTE } from '../api';
import { C, LINK_COLOR } from '../theme';
import { T, Btn, Card, Chip } from '../ui';
import RouteMap from '../RouteMap';

function Stat({ label, value, color }) {
  return (
    <Card style={{ flexGrow: 1, flexBasis: 140, padding: 12 }}>
      <T style={{ color: C.mute, fontSize: 11, letterSpacing: 0.8 }}>{label.toUpperCase()}</T>
      <T head style={{ fontSize: 24, color: color || C.text, marginTop: 2 }}>{value}</T>
    </Card>
  );
}

// Live screen: offline route map + vitals. Polls the backend every 2 s.
export default function MapScreen({ profile, onAlert, hasAlert }) {
  const [status, setStatus] = useState(null);
  const [live, setLive] = useState(false);
  const [route, setRoute] = useState(DEFAULT_ROUTE);

  const refresh = async () => {
    const { data, live } = await fetchStatus(profile.childId);
    setStatus(data);
    setLive(live);
  };

  useEffect(() => {
    fetchRoute().then(setRoute);
    refresh();
    const t = setInterval(refresh, 2000);
    const t2 = setInterval(() => fetchRoute().then(setRoute), 8000);
    return () => { clearInterval(t); clearInterval(t2); };
  }, []);

  const last = status?.last;
  const link = last?.link || 'direct';

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 12 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <T head style={{ fontSize: 26 }}>{profile.childName}</T>
        <Chip label={live ? 'LIVE FROM BACKEND' : 'MOCK DATA · BACKEND OFFLINE'} color={live ? C.green : C.amber} />
      </View>

      <RouteMap route={route} last={last} trail={status?.trail || []} offRouteM={status?.off_route_m || 0} />
      {!last && <T style={{ color: C.mute }}>Waiting for the band. Press “Play demo” in the Demo tab, or start the simulator.</T>}

      {last && (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <Stat label="Heart rate" value={`${last.hr} bpm`} color={last.hr > 130 ? C.red : C.text} />
          <Stat label="Skin gap" value={`${last.skin_distance_cm} cm`} color={last.skin_distance_cm > 2.5 ? C.red : C.text} />
          <Stat label="Battery" value={`${last.battery}%`} />
          <Stat label="Link" value={link} color={LINK_COLOR[link] || C.text} />
          <Stat label="Off route" value={`${status.off_route_m ?? '?'} m`} color={(status.off_route_m || 0) > route.off_route_dist_m ? C.red : C.text} />
          <Stat label="Status" value={status.status} color={status.status === 'alert' ? C.red : C.green} />
        </View>
      )}
      {last && link === 'buffered' && (
        <T style={{ color: C.orange, fontSize: 12 }}>Delivered late from the band’s memory after it was offline.</T>
      )}

      <View style={{ gap: 8 }}>
        <Btn title="Refresh" kind="ghost" onPress={refresh} />
        <Btn title={hasAlert ? 'Open latest alert' : 'Open sample alert (demo)'} kind="danger" onPress={onAlert} />
      </View>
    </ScrollView>
  );
}
