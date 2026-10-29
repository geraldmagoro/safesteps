import { Platform, View } from 'react-native';
import { C } from './theme';
import { T } from './ui';

// Offline route map: no tiles, no keys, no internet. Draws the planned route,
// the child's recent trail and current position (plus alert location) as SVG.
// Web only (the demo target); native shows coordinates instead.
const W = 340;
const H = 250;
const PAD = 34;

export default function RouteMap({ route, last, trail = [], alertLoc, offRouteM }) {
  const pts = [route.home, route.spaza, route.school];
  const extra = [...trail, ...(last ? [[last.gps_lat, last.gps_lon]] : []), ...(alertLoc ? [alertLoc] : [])];
  const all = [...pts, ...extra];
  const lat0 = all.reduce((a, p) => a + p[0], 0) / all.length;
  const kx = Math.cos((lat0 * Math.PI) / 180);
  const xs = all.map((p) => p[1] * kx);
  const ys = all.map((p) => p[0]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const span = Math.max(maxX - minX, maxY - minY, 0.0004);
  const scale = (Math.min(W, H) - PAD * 2) / span;
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
  const P = (p) => [W / 2 + (p[1] * kx - cx) * scale, H / 2 - (p[0] - cy) * scale];
  const metresPerPx = (1 / scale) * 110540;
  const barM = [20, 50, 100, 200, 500].find((m) => m / metresPerPx > 40) || 500;
  const barPx = barM / metresPerPx;

  if (Platform.OS !== 'web') {
    return <T style={{ color: C.mute }}>{last ? `${last.gps_lat.toFixed(5)}, ${last.gps_lon.toFixed(5)}` : 'waiting for GPS…'}</T>;
  }

  const line = pts.map((p) => P(p).join(',')).join(' ');
  const trailLine = trail.map((p) => P(p).join(',')).join(' ');
  const me = last ? P([last.gps_lat, last.gps_lon]) : null;
  const al = alertLoc ? P(alertLoc) : null;
  const names = ['HOME', 'SPAZA', 'SCHOOL'];
  const hot = offRouteM > (route.off_route_dist_m || 15);

  return (
    <View style={{ borderRadius: 14, overflow: 'hidden', borderWidth: 1, borderColor: C.line }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', background: '#12100C' }}>
        {[1, 2, 3].map((i) => (
          <line key={`v${i}`} x1={(W / 4) * i} y1="0" x2={(W / 4) * i} y2={H} stroke="#2A241B" strokeWidth="1" />
        ))}
        {[1, 2, 3].map((i) => (
          <line key={`h${i}`} x1="0" y1={(H / 4) * i} x2={W} y2={(H / 4) * i} stroke="#2A241B" strokeWidth="1" />
        ))}
        <polyline points={line} fill="none" stroke={C.orange} strokeWidth="3" strokeDasharray="7 6" strokeLinecap="round" strokeLinejoin="round" opacity="0.9" />
        {trail.length > 1 && <polyline points={trailLine} fill="none" stroke={C.blue} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />}
        {pts.map((p, i) => {
          const [x, y] = P(p);
          return (
            <g key={names[i]}>
              <circle cx={x} cy={y} r="6" fill="#12100C" stroke={C.orange} strokeWidth="2.5" />
              <text x={x + 10} y={y - 8} fill={C.mute} fontSize="10" fontFamily="Consolas, monospace" letterSpacing="1">{names[i]}</text>
            </g>
          );
        })}
        {al && (
          <g>
            <circle cx={al[0]} cy={al[1]} r="15" fill="none" stroke={C.red} strokeWidth="2" opacity="0.6" />
            <circle cx={al[0]} cy={al[1]} r="6" fill={C.red} />
          </g>
        )}
        {me && (
          <g>
            <circle cx={me[0]} cy={me[1]} r="11" fill={hot ? C.red : C.green} opacity="0.25" />
            <circle cx={me[0]} cy={me[1]} r="5.5" fill={hot ? C.red : C.green} stroke="#fff" strokeWidth="1.5" />
          </g>
        )}
        <line x1="14" y1={H - 14} x2={14 + barPx} y2={H - 14} stroke={C.mute} strokeWidth="2" />
        <text x="14" y={H - 20} fill={C.mute} fontSize="10" fontFamily="Consolas, monospace">{barM} m</text>
      </svg>
      <View style={{ position: 'absolute', right: 10, top: 8 }}>
        <T mono style={{ color: C.mute, fontSize: 10 }}>OFFLINE MAP · no internet needed</T>
      </View>
    </View>
  );
}
