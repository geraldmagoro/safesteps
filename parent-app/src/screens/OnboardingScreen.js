import { useState } from 'react';
import { View, Text, TextInput, Button, StyleSheet, ScrollView, Switch } from 'react-native';

// Onboarding: school address, route notes, 5 MANDATORY emergency contacts,
// child photo placeholder, favorite-route saving, Trip Mode with supervisor
// contacts. All validation is local for the MVP.
export default function OnboardingScreen({ onDone }) {
  const [school, setSchool] = useState('');
  const [route, setRoute] = useState('Home -> Spaza (left) -> School');
  const [childName, setChildName] = useState('');
  const [photo, setPhoto] = useState(null);
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
      childName, school, route, contacts, photo, childId: 'child-001',
      favoriteRoute: favName.trim() || null,
      tripMode,
      supervisors: tripMode ? filledSupervisors : [],
    });
  };

  return (
    <ScrollView contentContainerStyle={styles.wrap}>
      <Text style={styles.title}>SafeSteps setup</Text>

      <Text style={styles.label}>Child name</Text>
      <TextInput style={styles.input} value={childName} onChangeText={setChildName}
        placeholder="e.g. Naledi" />

      <Text style={styles.label}>Child photo</Text>
      <Button title={photo ? 'Photo attached ✓' : 'Attach photo'}
        onPress={() => setPhoto('photo-placeholder.jpg')} />

      <Text style={styles.label}>School address</Text>
      <TextInput style={styles.input} value={school} onChangeText={setSchool}
        placeholder="e.g. 12 Mooki St, Orlando East" />

      <Text style={styles.label}>Route</Text>
      <TextInput style={styles.input} value={route} onChangeText={setRoute} />

      <Text style={styles.label}>Save as Favorite</Text>
      <TextInput style={styles.input} value={favName} onChangeText={setFavName}
        placeholder="e.g. School run (optional)" />

      <View style={styles.row}>
        <Text style={styles.label}>Trip Mode</Text>
        <Switch value={tripMode} onValueChange={setTripMode} />
      </View>
      {tripMode ? (
        <View>
          <Text style={styles.hint}>Supervisor contacts (min 2) — notified first on Trip Mode alerts.</Text>
          {supervisors.map((s, i) => (
            <TextInput key={i} style={styles.input} value={s}
              onChangeText={(v) => setSupervisor(i, v)}
              placeholder={`Supervisor ${i + 1} phone`} keyboardType="phone-pad" />
          ))}
          <Button title="+ Add supervisor"
            onPress={() => setSupervisors([...supervisors, ''])} />
        </View>
      ) : null}

      <Text style={styles.label}>Emergency contacts (5 required)</Text>
      {contacts.map((c, i) => (
        <TextInput key={i} style={styles.input} value={c}
          onChangeText={(v) => setContact(i, v)}
          placeholder={`Contact ${i + 1} phone`} keyboardType="phone-pad" />
      ))}

      {error ? <Text style={styles.error}>{error}</Text> : null}
      <Button title="Start protecting" onPress={submit} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 20, gap: 6 },
  title: { fontSize: 24, fontWeight: 'bold', marginBottom: 10 },
  label: { fontWeight: '600', marginTop: 8 },
  input: { borderWidth: 1, borderColor: '#999', borderRadius: 6, padding: 8, marginTop: 2 },
  error: { color: 'red', marginVertical: 8 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 },
  hint: { color: '#666', fontSize: 12, marginTop: 4 },
});
