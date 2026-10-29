import { Pressable, Text, TextInput, View } from 'react-native';
import { C, FONT } from './theme';

// Themed text: Text defaults would ignore the dark theme and fonts.
export function T({ style, mono, head, ...p }) {
  return (
    <Text {...p}
      style={[{ color: C.text, fontFamily: mono ? FONT.mono : head ? FONT.head : FONT.body }, style]} />
  );
}

const KINDS = {
  primary: { bg: C.orange, fg: '#1A1308', border: C.orange },
  danger: { bg: C.red, fg: '#fff', border: C.red },
  ok: { bg: C.green, fg: '#06170E', border: C.green },
  ghost: { bg: 'transparent', fg: C.text, border: C.line },
};

export function Btn({ title, onPress, kind = 'primary', small, disabled }) {
  const k = KINDS[kind] || KINDS.primary;
  return (
    <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button"
      style={({ pressed }) => ({
        backgroundColor: k.bg, borderColor: k.border, borderWidth: 1, borderRadius: 10,
        paddingVertical: small ? 8 : 13, paddingHorizontal: small ? 14 : 18, alignItems: 'center',
        opacity: disabled ? 0.45 : pressed ? 0.8 : 1,
      })}>
      <T style={{ color: k.fg, fontWeight: '700', fontSize: small ? 13 : 15, letterSpacing: 0.3 }}>{title}</T>
    </Pressable>
  );
}

export function Input(p) {
  return (
    <TextInput placeholderTextColor={C.mute} {...p}
      style={[{ borderWidth: 1, borderColor: C.line, borderRadius: 10, padding: 11, marginTop: 4,
        backgroundColor: C.panel2, color: C.text, fontFamily: FONT.body, fontSize: 15 }, p.style]} />
  );
}

export function Card({ children, style }) {
  return (
    <View style={[{ backgroundColor: C.panel, borderColor: C.line, borderWidth: 1, borderRadius: 14, padding: 14 }, style]}>
      {children}
    </View>
  );
}

export function Chip({ label, color = C.mute }) {
  return (
    <View style={{ borderColor: color, borderWidth: 1, borderRadius: 99, paddingVertical: 2, paddingHorizontal: 9, alignSelf: 'flex-start' }}>
      <T style={{ color, fontSize: 11, fontWeight: '700', letterSpacing: 0.5 }}>{label}</T>
    </View>
  );
}
