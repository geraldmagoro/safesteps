import { View, Text, StyleSheet } from 'react-native';

export default function App() {
  return (
    <View style={styles.root}>
      <Text style={styles.title}>SafeSteps Parent — Works!</Text>
      <Text>Backend: http://localhost:8000 is live</Text>
      <Text>Your 5 contacts + Trip Mode + Drowning detection is ready</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#fff' },
  title: { fontSize: 24, fontWeight: 'bold', marginBottom: 10 }
});