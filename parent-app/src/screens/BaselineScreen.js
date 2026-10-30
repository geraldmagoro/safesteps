import { useEffect, useState } from 'react';
import { Platform, ScrollView, View } from 'react-native';
import { baselineGet, baselineSeed, baselineAnalyze, baselineApprove, baselineReset, demoPlay, demoStatus } from '../api';
import { C } from '../theme';
import { T, Btn, Card, Chip } from '../ui';

const CHILD = 'child-001';
const W = 340;
const H = 190;

// Peak heart rate while still, per trip, against the default and personal thresholds.
function HrBars({ trips, defaultHr, proposed, active }) {
  if (Platform.OS !== 'web' || !trips.length) return null;
  const lo = 80, hi = 160;
  const y = (v) => H - 24 - ((v - lo) / (hi - lo)) * (H - 44);
  const bw = (W - 40) / trips.length;
  const line = (v, color, label, dash) => (
    <g key={label}>
      <line x1="30" x2={W - 6} y1={y(v)} y2={y(v)} stroke={color} strokeWidth="1.6" strokeDasharray={dash || '0'} />
      <text x={W - 8} y={y(v) - 4} fill={color} fontSize="10" textAnchor="end" fontFamily="Consolas, monospace">{label} {v}</text>
    </g>
  );
  return (
    <View style={{ borderRadius: 12, overflow: 'hidden', borderWidth: 1, borderColor: C.line }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', background: '#12100C' }}>
        {[100, 120, 140].map((v) => (
          <g key={v}>
            <line x1="30" x2={W - 6} y1={y(v)} y2={y(v)} stroke="#2A241B" strokeWidth="1" />
            <text x="4" y={y(v) + 3} fill={C.mute} fontSize="9" fontFamily="Consolas, monospace">{v}</text>
          </g>
        ))}
        {trips.map((t, i) => {
          const v = t.hr_peak_while_still;
          return <rect key={t.day} x={34 + i * bw} y={y(v)} width={bw - 4} height={H - 24 - y(v)} rx="2"
            fill={v > defaultHr ? C.red : C.orange} opacity={t.late_run ? 1 : 0.7} />;
        })}
        {line(defaultHr, C.mute, 'default', '5 4')}
        {proposed && !active ? line(proposed, C.blue, 'proposed', '5 4') : null}
        {active ? line(active, C.green, 'approved') : null}
        <text x="34" y={H - 8} fill={C.mute} fontSize="9" fontFamily="Consolas, monospace">trips, oldest to newest · bar = peak heart rate while still</text>
      </svg>
    </View>
  );
}

function Stat({ label, value }) {
  return (
    <Card style={{ flexGrow: 1, flexBasis: 150, padding: 12 }}>
      <T style={{ color: C.mute, fontSize: 11, letterSpacing: 0.8 }}>{label.toUpperCase()}</T>
      <T head style={{ fontSize: 20, marginTop: 2 }}>{value}</T>
    </Card>
  );
}

function Step({ n, title, children }) {
  return (
    <Card style={{ gap: 8 }}>
      <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
        <T head style={{ color: C.orange, fontSize: 22 }}>{n}</T>
        <T head style={{ fontSize: 18 }}>{title}</T>
      </View>
      {children}
    </Card>
  );
}

export default function BaselineScreen() {
  const [b, setB] = useState(null);
  const [err, setErr] = useState('');
  const [run, setRun] = useState({ running: false, log: [] });

  const load = async () => {
    try { setB(await baselineGet(CHILD)); setErr(''); } catch (e) { setErr('Backend not reachable.'); }
  };
  useEffect(() => {
    load();
    const t = setInterval(async () => {
      load();
      try { setRun(await demoStatus()); } catch (e) { /* offline */ }
    }, 1500);
    return () => clearInterval(t);
  }, []);

  const act = (fn) => async () => {
    try { setB(await fn(CHILD)); setErr(''); } catch (e) {
      setErr(String(e.message || e).includes('400') ? 'Not ready: load the history, then analyse, then approve.' : 'Could not do that. Is the backend running?');
    }
  };
  const playRunner = async () => {
    try { await demoPlay('runner_crossing'); } catch (e) { setErr('A demo is already running. Wait a few seconds.'); }
  };

  const stats = b?.stats;
  const proposal = b?.proposal;
  const running = b?.status === 'running';

  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 14 }}>
      <View>
        <T head style={{ fontSize: 28 }}>Personal baseline</T>
        <T style={{ color: C.mute, marginTop: 2 }}>
          Learns what is normal for this child, so a heart-rate alert after running does not look the same as one on a calm walk.
          The Meta Model proposes, the server limits the proposal, and the parent approves. Band-off, drowning, faint and off-route rules never change.
        </T>
      </View>
      {err ? <T style={{ color: C.amber }}>{err}</T> : null}

      <Step n="1" title="Load her recent trips">
        <T style={{ color: C.mute, fontSize: 13 }}>The demo uses three weeks of SYNTHETIC trips. The method works on real trip logs, which the app does not collect yet.</T>
        <Btn small title={b?.has_history ? 'Reload synthetic history' : 'Load synthetic history'} onPress={act(baselineSeed)} />
        {b?.has_history ? <Chip label="SYNTHETIC DEMO DATA" color={C.amber} /> : null}
        {stats ? (
          <View style={{ gap: 10 }}>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
              <Stat label="Normal walking heart rate" value={`${stats.hr_walk_range_normal_days[0]}–${stats.hr_walk_range_normal_days[1]} bpm`} />
              <Stat label="Late-run days" value={`${stats.late_run_days} of ${stats.trips}`} />
              <Stat label="Peak while still, late-run days" value={`${stats.hr_peak_while_still_late_run_days[0]}–${stats.hr_peak_while_still_late_run_days[1]} bpm`} />
              <Stat label="Usual departure" value={`${stats.depart_median} (${stats.depart_range[0]}–${stats.depart_range[1]})`} />
            </View>
            <T style={{ color: C.orange, fontSize: 13 }}>
              The default rule ({b.default_hr_spike} bpm) would have raised {stats.days_that_would_fire_default_hr_rule} alerts in these {stats.trips} trips.
            </T>
            <HrBars trips={b.trips} defaultHr={b.default_hr_spike} proposed={proposal?.suggested_hr_spike_final} active={b.approved ? b.active_hr_spike : null} />
          </View>
        ) : null}
      </Step>

      <Step n="2" title="Ask the Meta Model">
        <Btn small title={running ? 'Analysing…' : 'Analyse with Meta Model'} disabled={!b?.has_history || running} onPress={act(baselineAnalyze)} />
        {b?.status === 'error' ? <T style={{ color: C.amber }}>AI unavailable ({b.error}). Nothing changed.</T> : null}
        {proposal ? (
          <View style={{ gap: 4 }}>
            <T>{proposal.summary}</T>
            {(proposal.false_alarm_patterns || []).map((p, i) => <T key={i} style={{ color: C.mute }}>· {p}</T>)}
            <T style={{ fontWeight: '700', color: C.blue, marginTop: 4 }}>
              Proposed heart-rate-while-still threshold: {proposal.suggested_hr_spike_final} bpm (default {b.default_hr_spike})
            </T>
            {proposal.guardrail?.adjusted ? <T style={{ color: C.amber, fontSize: 12 }}>Server limit applied: {proposal.guardrail.reason}</T> : null}
            <T style={{ color: C.mute, fontSize: 12 }}>Trade-off: {proposal.trade_off}</T>
            <T mono style={{ color: C.mute, fontSize: 11 }}>model: {proposal.model} · confidence {Math.round((proposal.confidence || 0) * 100)}%</T>
          </View>
        ) : null}
      </Step>

      <Step n="3" title="Parent decides">
        <T style={{ color: C.mute, fontSize: 13 }}>{b?.safety_note}</T>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <View style={{ flex: 1 }}><Btn kind="ok" title="Approve for her" disabled={!proposal} onPress={act(baselineApprove)} /></View>
          <View style={{ flex: 1 }}><Btn kind="ghost" title="Reset to default" onPress={act(baselineReset)} /></View>
        </View>
        <T style={{ fontWeight: '700', color: b?.approved ? C.green : C.text }}>
          Active threshold: {b?.active_hr_spike ?? 130} bpm {b?.approved ? '(approved personal baseline)' : '(default)'}
        </T>
      </Step>

      <Step n="4" title="See the difference">
        <T style={{ color: C.mute, fontSize: 13 }}>
          Plays a late, running child who stops at a crossing at 138 bpm. Run it with the default, approve a baseline, then run it again.
        </T>
        <Btn small title={run.running ? 'Running…' : 'Play: runner at the crossing'} disabled={run.running} onPress={playRunner} />
        {run.scenario === 'runner_crossing' && run.log.length ? (
          <View style={{ gap: 2 }}>
            {run.log.slice(-7).map((e, i) => (
              <T key={i} mono style={{ fontSize: 12, color: e.kind === 'alert' ? C.red : e.kind === 'note' ? C.amber : C.text }}>[{e.kind}] {e.msg}</T>
            ))}
          </View>
        ) : null}
      </Step>
    </ScrollView>
  );
}
