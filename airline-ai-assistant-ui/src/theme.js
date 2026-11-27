import { createTheme } from '@mui/material/styles';

// App palette: #36393B, #A5D8FF, #AFD0D6, #BFB6BB, #C49799.
// AUTUMN is kept as the export name so existing components keep working.
export const AUTUMN = {
  sienna: '#36393B',   // charcoal: primary, headings
  amber: '#A5D8FF',    // sky: accent glow, highlights
  ember: '#C49799',    // rose: secondary accent
  moss: '#5E8E95',     // deep teal: compliance section
  plum: '#8E8590',     // deep mauve: knowledge section
  teal: '#5C9CCB',     // deep sky: operations section
  walnut: '#36393B',
  cream: '#F6F4F5',
  sand: '#E3DDE0',
  ink: '#36393B',
  muted: '#6B6669',
};

export const TONES = {
  charcoal: { bg: 'linear-gradient(135deg, #4A4E51 0%, #36393B 100%)', fg: '#FFFFFF' },
  sky: { bg: 'linear-gradient(135deg, #D6F0FF 0%, #A5D8FF 100%)', fg: '#36393B' },
  teal: { bg: 'linear-gradient(135deg, #D9E9EC 0%, #AFD0D6 100%)', fg: '#36393B' },
  mauve: { bg: 'linear-gradient(135deg, #DCD5DA 0%, #BFB6BB 100%)', fg: '#36393B' },
  rose: { bg: 'linear-gradient(135deg, #DDBDBE 0%, #C49799 100%)', fg: '#36393B' },
};

export const theme = createTheme({
  palette: {
    primary: { main: '#36393B', light: '#5A5F62', dark: '#222426', contrastText: '#FFFFFF' },
    secondary: { main: '#8E8590', contrastText: '#FFFFFF' },
    success: { main: '#4E7D84', contrastText: '#FFFFFF' },
    warning: { main: '#C49799', contrastText: '#36393B' },
    error: { main: '#8E4F55', contrastText: '#FFFFFF' },
    info: { main: '#4F8FBF', contrastText: '#FFFFFF' },
    background: { default: '#F6F4F5', paper: '#FFFFFF' },
    text: { primary: '#36393B', secondary: '#6B6669' },
    divider: '#E3DDE0',
  },
  shape: { borderRadius: 16 },
  typography: {
    fontFamily: '"Plus Jakarta Sans", Inter, system-ui, sans-serif',
    h4: { fontWeight: 700, letterSpacing: '-0.02em' },
    h5: { fontWeight: 700, letterSpacing: '-0.015em' },
    overline: { letterSpacing: '0.12em', fontWeight: 700 },
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          border: '1px solid #E3DDE0',
          boxShadow: '0 12px 32px -22px rgba(54,57,59,0.35)',
          transition: 'transform .3s ease, box-shadow .3s ease',
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { textTransform: 'none', borderRadius: 999, fontWeight: 600, paddingInline: 18, boxShadow: 'none' },
        containedPrimary: {
          background: 'linear-gradient(135deg, #4A4E51 0%, #36393B 100%)',
          boxShadow: '0 8px 18px -10px rgba(54,57,59,0.7)',
          '&:hover': { background: 'linear-gradient(135deg, #5A5F62 0%, #2A2C2E 100%)' },
        },
      },
    },
    MuiChip: { styleOverrides: { root: { borderRadius: 999 } } },
    MuiTab: { styleOverrides: { root: { textTransform: 'none', fontWeight: 600, minHeight: 44 } } },
    MuiTabs: { styleOverrides: { indicator: { height: 3, borderRadius: 3, background: '#A5D8FF' } } },
    MuiDataGrid: {
      styleOverrides: {
        root: { border: 'none', borderRadius: 16 },
        columnHeaders: { backgroundColor: '#EEEAEC', borderBottom: '1px solid #E3DDE0' },
        columnHeaderTitle: { fontWeight: 700, color: '#36393B' },
        row: { '&:hover': { backgroundColor: '#F1ECEF' } },
      },
    },
  },
});
