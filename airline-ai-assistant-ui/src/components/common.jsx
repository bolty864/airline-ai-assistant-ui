import { Alert, Box, Button, Card, CardContent, Chip, Skeleton, Stack, Typography } from '@mui/material';
import { TONES, AUTUMN } from '../theme.js';

const COLORS = {
  HIGH: 'error', CRITICAL: 'error', MEDIUM: 'warning', LOW: 'success',
  MAPPED: 'info', PENDING: 'default', MAPPING: 'info', NEEDS_REVIEW: 'warning', UNMAPPED: 'default', ERROR: 'error',
  PROPOSED: 'warning', CONFIRMED: 'success', REJECTED: 'error', CHANGES_REQUESTED: 'warning',
  OPEN: 'default', IN_PROGRESS: 'info', REVIEW: 'secondary', DONE: 'success', CANCELLED: 'default',
  New: 'primary', Processing: 'warning', Analyzed: 'info', Mapped: 'info', Published: 'success',
  Compliant: 'success', Partial: 'warning', 'Non-Compliant': 'error',
  Active: 'success', Draft: 'default', Approved: 'success', 'Pending review': 'warning',
  Healthy: 'success', Running: 'info', 'Self-Healing': 'secondary',
  COMPLETED: 'success', PARTIAL: 'warning', NO_OBLIGATIONS: 'default', SKIPPED_UNCHANGED: 'default',
  SELF_HEALED: 'success', HEAL_FAILED: 'error',
};

export function StatusChip({ value }) {
  return (
    <Chip
      size="small"
      label={value ?? '—'}
      color={COLORS[value] || 'default'}
      variant="filled"
      sx={{ fontWeight: 700, letterSpacing: '0.01em' }}
    />
  );
}

export function fmtDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}

export function PageHeader({ eyebrow, title, subtitle, actions }) {
  return (
    <Stack
      direction={{ xs: 'column', md: 'row' }}
      justifyContent="space-between"
      alignItems={{ xs: 'flex-start', md: 'flex-end' }}
      spacing={2}
      mb={3.5}
      className="page-enter"
    >
      <Box>
        {eyebrow && (
          <Typography variant="overline" sx={{ color: '#5C9CCB', display: 'block' }}>
            {eyebrow}
          </Typography>
        )}
        <Typography
          variant="h4"
          sx={{
            background: `linear-gradient(90deg, ${AUTUMN.ink} 0%, #4A4E51 60%, #5C9CCB 100%)`,
            WebkitBackgroundClip: 'text',
            backgroundClip: 'text',
            color: 'transparent',
          }}
        >
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="body2" color="text.secondary" mt={0.5}>
            {subtitle}
          </Typography>
        )}
      </Box>
      {actions && <Stack direction="row" spacing={1}>{actions}</Stack>}
    </Stack>
  );
}

// Shows a skeleton while loading, an error with retry, or the children.
export function LoadState({ loading, error, onRetry, children }) {
  if (loading) {
    return (
      <Stack spacing={1.5}>
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} variant="rounded" height={72} sx={{ borderRadius: 4 }} />
        ))}
      </Stack>
    );
  }
  if (error) {
    return (
      <Alert
        severity="error"
        action={onRetry && <Button color="inherit" size="small" onClick={onRetry}>Retry</Button>}
      >
        {error}
      </Alert>
    );
  }
  return children;
}

export function EmptyState({ text }) {
  return (
    <Box sx={{ py: 5, textAlign: 'center', color: 'text.secondary' }}>
      <Typography variant="body2">{text}</Typography>
    </Box>
  );
}

// `accent` keeps the old hex prop working; each value maps to a palette tone.
const ACCENT_TO_TONE = {
  '#ed8c00': 'sky',
  '#d32f2f': 'rose',
  '#0288d1': 'teal',
  '#2e7d32': 'mauve',
};

export function KpiCard({ label, value, hint, accent, tone }) {
  const t = TONES[tone || ACCENT_TO_TONE[accent] || 'charcoal'];
  return (
    <Card
      className="lift"
      sx={{
        position: 'relative',
        overflow: 'hidden',
        background: t.bg,
        color: t.fg,
        border: 'none',
        boxShadow: '0 18px 36px -20px rgba(54,57,59,0.45)',
        '&::after': {
          content: '""',
          position: 'absolute',
          right: -28,
          top: -28,
          width: 110,
          height: 110,
          borderRadius: '50%',
          background: 'rgba(255,255,255,0.3)',
        },
      }}
    >
      <CardContent sx={{ position: 'relative', zIndex: 1 }}>
        <Typography variant="overline" sx={{ opacity: 0.8 }}>{label}</Typography>
        <Typography variant="h3" fontWeight={800} lineHeight={1.1} mt={0.5}>{value}</Typography>
        {hint && <Typography variant="caption" sx={{ opacity: 0.8 }}>{hint}</Typography>}
      </CardContent>
    </Card>
  );
}

export function Panel({ title, action, children, sx }) {
  return (
    <Card sx={{ ...sx, transition: 'transform .3s ease, box-shadow .3s ease' }} className="lift">
      <CardContent>
        {(title || action) && (
          <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1.5}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <Box sx={{ width: 4, height: 18, borderRadius: 4, background: 'linear-gradient(#A5D8FF, #C49799)' }} />
              <Typography variant="subtitle1" fontWeight={700}>{title}</Typography>
            </Stack>
            {action}
          </Stack>
        )}
        {children}
      </CardContent>
    </Card>
  );
}
