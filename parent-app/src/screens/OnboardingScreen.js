import { useState } from 'react';
import { View, StyleSheet, ScrollView, Switch } from 'react-native';
import { C } from '../theme';
import { T, Btn, Input } from '../ui';

// Onboarding: school address, route notes, 5 MANDATORY emergency contacts,
// child photo placeholder, favorite-route saving, Trip Mode with supervisor
// contacts. All validation is local for the MVP.
export default function OnboardingScreen({ onDone }) {
  const [school, setSchool] = useState('');
  const [route, setRoute] = useState('Home -> Spaza (left) -> School');
  const [childName, setChildName] = useState('');
  const [photo, setPhoto] = useState(null);
  const [language, setLanguage] = useState('');
  const [contacts, setContacts] = useState(['', '', '', '', '']);
  const [favName, setFavName] = useState('');
  const [tripMode, setTripMode] = useState(false);
  const [supervisors, setSupervisors] = useState(['', '']);
  const [error, setError] = useState('');

  const setContact = (i, v) => {
    const next = [...contacts];
    next[i] = v;
    setContacts(next);
  };

  const setSupervisor = (i, v) => {
    const next = [...supervisors];
    next[i] = v;
    setSupervisors(next);
  };

  const submit = () => {
    if (!childName.trim() || !school.trim()) {
      setError('Child name and school address are required.');
      return;
    }
    if (contacts.some((c) => !c.trim())) {
      setError('All 5 emergency contacts are mandatory.');
      return;
    }
    const filledSupervisors = supervisors.map((s) => s.trim()).filter(Boolean);
    if (tripMode && filledSupervisors.length < 2) {
      setError('Trip Mode needs at least 2 supervisor contacts.');
      return;
    }
    setError('');
    onDone({
      childName, school, route, contacts, photo, language: language.trim(), childId: 'child-001',
      favoriteRoute: favName.trim() || null,
      tripMode,
      supervisors: tripMode ? filledSupervisors : [],
    });
  };

  return (
    <ScrollView contentContainerStyle={styles.wrap}>
      <T head style={styles.title}>SafeSteps setup</T>

      <T style={styles.label}>Child name</T>
      <Input value={childName} onChangeText={setChildName}
        placeholder="e.g. Naledi" />

      <T style={styles.label}>Child photo</T>
      <Btn title={photo ? 'Photo attached ✓' : 'Attach photo'}
        onPress={() => setPhoto('photo-placeholder.jpg')} />

      <T style={styles.label}>Your language for alerts (optional)</T>
      <Input value={language} onChangeText={setLanguage}
        placeholder="e.g. isiZulu, Sesotho, Afrikaans" />

      <T style={styles.label}>School address</T>
      <Input value={school} onChangeText={setSchool}
        placeholder="e.g. 12 Mooki St, Orlando East" />

      <T style={styles.label}>Route</T>
      <Input value={route} onChangeText={setRoute} />

      <T style={styles.label}>Save as Favorite</T>
      <Input value={favName} onChangeText={setFavName}
        placeholder="e.g. School run (optional)" />

      <View style={styles.row}>
        <T style={styles.label}>Trip Mode</T>
        <Switch value={tripMode} onValueChange={setTripMode} trackColor={{ true: C.orange, false: C.line }} thumbColor={C.text} />
      </View>
      {tripMode ? (
        <View>
          <T style={styles.hint}>Supervisor contacts (min 2) — notified first on Trip Mode alerts.</T>
          {supervisors.map((s, i) => (
            <Input key={i} value={s}
              onChangeText={(v) => setSupervisor(i, v)}
              placeholder={`Supervisor ${i + 1} phone`} keyboardType="phone-pad" />
          ))}
          <Btn title="+ Add supervisor"
            onPress={() => setSupervisors([...supervisors, ''])} />
        </View>
      ) : null}

      <T style={styles.label}>Emergency contacts (5 required)</T>
      {contacts.map((c, i) => (
        <Input key={i} value={c}
          onChangeText={(v) => setContact(i, v)}
          placeholder={`Contact ${i + 1} phone`} keyboardType="phone-pad" />
      ))}

      {error ? <T style={styles.error}>{error}</T> : null}
      <Btn title="Start protecting" onPress={submit} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 20, gap: 6 },
  title: { fontSize: 26, marginBottom: 10 },
  label: { fontWeight: '600', marginTop: 8, color: C.text },
  input: { borderWidth: 1, borderColor: '#999', borderRadius: 6, padding: 8, marginTop: 2 },
  error: { color: C.red, marginVertical: 8 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 },
  hint: { color: C.mute, fontSize: 12, marginTop: 4 },
});
