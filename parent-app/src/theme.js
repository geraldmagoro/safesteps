// SafeSteps brand: warm dark theme + logo orange. Fonts fall back to system
// stacks, so the app looks right with no internet.
export const C = {
  bg: '#16130F', panel: '#1E1A14', panel2: '#26211A', line: '#3A3226',
  text: '#F5EFE0', mute: '#B8AE98', orange: '#DC8811', blue: '#6BB6FF',
  red: '#E55A3D', green: '#3BA873', amber: '#E0B03A',
};
export const FONT = {
  head: 'Fraunces, Georgia, "Times New Roman", serif',
  body: '"Instrument Sans", "Segoe UI", system-ui, sans-serif',
  mono: '"JetBrains Mono", Consolas, "Courier New", monospace',
};
export const LINK_COLOR = { direct: C.green, relay: C.blue, buffered: C.orange, sms: C.amber, offline: C.red };
