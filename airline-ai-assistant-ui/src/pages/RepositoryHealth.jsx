import { useState } from 'react';
import { Alert, Box, Button, Chip, LinearProgress, List, ListItem, ListItemIcon, ListItemText, Stack, Typography } from '@mui/material';
import { CheckCircleOutline, RadioButtonUnchecked } from '@mui/icons-material';
import { PageHeader, KpiCard, Panel, StatusChip, LoadState } from '../components/common.jsx';
import { useWorkspace } from '../data/WorkspaceContext.jsx';
import { api } from '../services/api.js';

const STEPS = ['Simulate file deletion', 'Watchdog scan and self-heal', 'Result'];

export default function RepositoryHealth() {
  const ws = useWorkspace();
  const health = ws.health;
  const [docCode, setDocCode] = useState(null);
  const [phase, setPhase] = useState('idle'); // idle | deleting | scanning | done | error
  const [scan, setScan] = useState(null);
  const [error, setError] = useState(null);

  const target = docCode ?? ws.documents[0]?.doc_code;
  const running = phase === 'deleting' || phase === 'scanning';
  const stepIndex = { idle: -1, deleting: 0, scanning: 1, done: 3, error: 1 }[phase];

  const run = async () => {
    if (!target) return;
    setScan(null);
    setError(null);
    try {
      setPhase('deleting');
      await api.simulateDelete(target);
      setPhase('scanning');
      const result = await api.watchdogScan();
      setScan(result);
      setPhase('done');
      ws.reload();
    } catch (e) {
      setError(e.message);
      setPhase('error');
    }
  };

  const progress = stepIndex < 0 ? 0 : Math.round((Math.min(stepIndex, 3) / STEPS.length) * 100);

  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Repository health"
        subtitle="Self-healing regulatory repository"
        actions={
          <Button variant="contained" onClick={run} disabled={running || !target}>
            {running ? 'Running…' : 'Run self-heal demo'}
          </Button>
        }
      />

      <LoadState loading={ws.loading} error={ws.error} onRetry={ws.reload}>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' }, gap: 2, mb: 2 }}>
          <KpiCard label="Regulatory documents" value={ws.documents.length} tone="teal" />
          <KpiCard label="Obligations extracted" value={ws.obligations.length} tone="sky" />
        </Box>

        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '3fr 2fr' }, gap: 2, mb: 2 }}>
          <Panel title="Self-heal run">
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" mb={2}>
              {ws.documents.slice(0, 12).map((d) => (
                <Chip
                  key={d.id}
                  label={d.doc_code}
                  clickable
                  color={d.doc_code === target ? 'primary' : 'default'}
                  onClick={() => setDocCode(d.doc_code)}
                  disabled={running}
                />
              ))}
            </Stack>
            <LinearProgress variant="determinate" value={progress} sx={{ height: 8, borderRadius: 4, mb: 2 }} />
            <List dense>
              {STEPS.map((label, i) => {
                const done = phase === 'done' || stepIndex > i;
                return (
                  <ListItem key={label} disableGutters>
                    <ListItemIcon sx={{ minWidth: 32 }}>
                      {done ? <CheckCircleOutline color="success" fontSize="small" /> : <RadioButtonUnchecked fontSize="small" />}
                    </ListItemIcon>
                    <ListItemText primary={label} />
                  </ListItem>
                );
              })}
            </List>

            {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}

            {scan && (
              <Box mt={2}>
                <Typography variant="body2" mb={1}>
                  Scanned {scan.scanned} · Healthy {scan.healthy} · Healed {scan.healed} · Failed {scan.failed}
                  {scan.skipped ? ' (scan already running)' : ''}
                </Typography>
                <Stack spacing={1}>
                  {(scan.actions ?? []).map((a, i) => (
                    <Stack key={`${a.doc_code}-${i}`} direction="row" spacing={1} alignItems="center">
                      <StatusChip value={a.outcome} />
                      <Typography variant="body2" fontWeight={600}>{a.doc_code}</Typography>
                      <Typography variant="caption" color="text.secondary">{a.reason}</Typography>
                    </Stack>
                  ))}
                </Stack>
              </Box>
            )}
          </Panel>

          <Panel title="System health">
            {health ? (
              <Stack spacing={1.5}>
                <Stack direction="row" justifyContent="space-between"><Typography variant="body2">Database</Typography><StatusChip value={health.database_connected ? 'Healthy' : 'ERROR'} /></Stack>
                <Stack direction="row" justifyContent="space-between"><Typography variant="body2">Blob storage</Typography><StatusChip value={health.blob_storage_connected ? 'Healthy' : 'ERROR'} /></Stack>
                <Stack direction="row" justifyContent="space-between"><Typography variant="body2">Storage mode</Typography><Typography variant="body2" fontWeight={700}>{health.storage_mode}</Typography></Stack>
                <Stack direction="row" justifyContent="space-between"><Typography variant="body2">Watchdog</Typography><StatusChip value={health.watchdog_active ? 'Self-Healing' : 'ERROR'} /></Stack>
                <Stack direction="row" justifyContent="space-between"><Typography variant="body2">Watchdog interval</Typography><Typography variant="body2" fontWeight={700}>{health.watchdog_interval_seconds}s</Typography></Stack>
                <Stack direction="row" justifyContent="space-between"><Typography variant="body2">LLM</Typography><StatusChip value={health.llm_configured ? 'Running' : 'ERROR'} /></Stack>
              </Stack>
            ) : (
              <Typography variant="body2" color="text.secondary">Health endpoint unavailable.</Typography>
            )}
          </Panel>
        </Box>
      </LoadState>
    </>
  );
}
