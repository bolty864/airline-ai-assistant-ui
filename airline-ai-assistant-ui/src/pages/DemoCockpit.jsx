import { useEffect, useState } from 'react';
import { Box, Button, Chip, Stack, Typography } from '@mui/material';
import { PageHeader, KpiCard, Panel, StatusChip, LoadState } from '../components/common.jsx';
import { useWorkspace, pendingAssets } from '../data/WorkspaceContext.jsx';

export default function DemoCockpit() {
  const ws = useWorkspace();
  const h = ws.health;

  const criticalGaps = ws.gaps.filter((g) => ['HIGH', 'CRITICAL'].includes(g.risk_rating) && g.gap_type !== 'No Gap').length;
  const published = ws.documents.filter((d) => /publish/i.test(d.status ?? '')).length;
  const pending = pendingAssets(ws.impacts).length;

  const workflow = [
    `${ws.documents.length} regulations`,
    `${ws.obligations.length} obligations`,
    `${ws.impacts.length} mapped`,
    `${criticalGaps} high gaps`,
    `${pending} awaiting approval`,
    `${published} published`,
  ];

  const agents = [
    { name: 'Monitoring agent', status: h ? 'Healthy' : 'ERROR' },
    { name: 'Extraction agent', status: ws.obligations.length ? 'Healthy' : 'Processing' },
    { name: 'Mapping agent', status: ws.impacts.length ? 'Healthy' : 'Running' },
    { name: 'Gap agent', status: ws.gaps.length ? 'Healthy' : 'Running' },
    { name: 'Repository agent', status: h?.watchdog_active ? 'Self-Healing' : 'Healthy' },
  ];

  // 0 = idle; 1..n = workflow steps lit so far (visual only)
  const [step, setStep] = useState(0);
  const total = workflow.length;
  const running = step > 0 && step < total;

  useEffect(() => {
    if (!running) return undefined;
    const t = setTimeout(() => setStep((s) => s + 1), 1000);
    return () => clearTimeout(t);
  }, [running, step]);

  return (
    <>
      <PageHeader
        eyebrow="Demo mode"
        title="Executive cockpit"
        subtitle="Live figures from the API, for the demo"
        actions={
          <Button variant="contained" onClick={() => setStep(1)} disabled={running || ws.loading}>
            Play live workflow
          </Button>
        }
      />

      <LoadState loading={ws.loading} error={ws.error} onRetry={ws.reload}>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(5, 1fr)' }, gap: 2, mb: 2 }}>
          <KpiCard label="Regulations" value={ws.documents.length} tone="sky" />
          <KpiCard label="Obligations" value={ws.obligations.length} tone="teal" />
          <KpiCard label="Critical gaps" value={criticalGaps} tone="rose" />
          <KpiCard label="Published" value={published} tone="mauve" />
          <KpiCard label="Avg coverage" value={ws.complianceScore == null ? '—' : `${ws.complianceScore}%`} tone="charcoal" />
        </Box>

        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 2fr' }, gap: 2, mb: 2 }}>
          <Panel title="Agent status">
            <Stack spacing={1.5}>
              {agents.map((a) => (
                <Stack key={a.name} direction="row" justifyContent="space-between" alignItems="center">
                  <Typography variant="body2">{a.name}</Typography>
                  <StatusChip value={a.status} />
                </Stack>
              ))}
            </Stack>
          </Panel>

          <Panel title="Live workflow">
            <Stack direction="row" useFlexGap flexWrap="wrap" spacing={1} alignItems="center">
              {workflow.map((label, i) => (
                <Box key={label} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Chip
                    label={label}
                    color={step > i ? 'success' : 'default'}
                    variant={step > i ? 'filled' : 'outlined'}
                  />
                  {i < total - 1 && <Typography color="text.secondary">→</Typography>}
                </Box>
              ))}
            </Stack>
            <Typography variant="caption" color="text.secondary" display="block" mt={2}>
              {step === 0 && 'Press "Play live workflow" to step through the chain.'}
              {step > 0 && step < total && 'Running…'}
              {step >= total && 'Workflow complete. Figures above are from the API.'}
            </Typography>
          </Panel>
        </Box>
      </LoadState>
    </>
  );
}
