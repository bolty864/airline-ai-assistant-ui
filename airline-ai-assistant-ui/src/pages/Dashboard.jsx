import { Alert, Box, Chip, List, ListItem, ListItemText, Stack, Typography } from '@mui/material';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { PageHeader, Panel, KpiCard, LoadState, StatusChip, fmtDate } from '../components/common.jsx';
import { useWorkspace, countBy, pendingAssets } from '../data/WorkspaceContext.jsx';

const CHIP_TINTS = ['#A5D8FF', '#AFD0D6', '#BFB6BB', '#C49799', '#D9CFD5'];

export default function Dashboard() {
  const ws = useWorkspace();

  const regulatorCounts = countBy(ws.documents, (d) => d.regulator);
  const statusCounts = countBy(ws.documents, (d) => d.status);
  const risk = ws.gapStats.by_risk ?? {};
  const criticalGaps = ws.gaps.filter((g) => ['HIGH', 'CRITICAL'].includes(g.risk_rating) && g.gap_type !== 'No Gap').length;
  const pending = pendingAssets(ws.impacts).length;
  const published = ws.documents.filter((d) => /publish/i.test(d.status ?? '')).length;
  const score = ws.complianceScore;
  const gauge = [{ value: score ?? 0 }, { value: 100 - (score ?? 0) }];
  const health = ws.health;

  return (
    <>
      <PageHeader
        eyebrow="Executive summary"
        title="Compliance posture"
        subtitle="Live view of regulatory compliance across sources, gaps and approvals"
      />

      <LoadState loading={ws.loading} error={ws.error} onRetry={ws.reload}>
        {/* Hero band */}
        <Box
          className="page-enter lift"
          sx={{
            position: 'relative',
            overflow: 'hidden',
            borderRadius: 5,
            p: { xs: 3, md: 4 },
            mb: 3,
            color: '#FFFFFF',
            background: 'linear-gradient(120deg, #2A2C2E 0%, #36393B 45%, #4A4E51 80%, #5C6266 100%)',
            boxShadow: '0 30px 60px -36px rgba(34,36,38,0.9)',
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', md: '1.4fr 1fr' },
            gap: 3,
            alignItems: 'center',
            '&::before': {
              content: '""', position: 'absolute', width: 380, height: 380, right: -120, top: -180,
              borderRadius: '50%', background: 'radial-gradient(circle, rgba(165,216,255,0.35), transparent 70%)',
            },
            '&::after': {
              content: '""', position: 'absolute', width: 260, height: 260, left: -90, bottom: -150,
              borderRadius: '50%', background: 'radial-gradient(circle, rgba(196,151,153,0.35), transparent 70%)',
            },
          }}
        >
          <Box sx={{ position: 'relative', zIndex: 1 }}>
            <Typography variant="overline" sx={{ opacity: 0.8 }}>Current status</Typography>
            <Typography variant="h4" fontWeight={800} lineHeight={1.2} mt={0.5}>
              {criticalGaps > 0
                ? `${criticalGaps} high-risk ${criticalGaps === 1 ? 'gap needs' : 'gaps need'} attention.`
                : 'No high-risk gaps found.'}
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" mt={2.5}>
              <Chip label={`${ws.obligations.length} obligations`} sx={{ bgcolor: 'rgba(255,255,255,0.14)', color: '#FFFFFF' }} />
              <Chip label={`${pending} awaiting approval`} sx={{ bgcolor: 'rgba(255,255,255,0.14)', color: '#FFFFFF' }} />
              <Chip label={`${published} published`} sx={{ bgcolor: 'rgba(255,255,255,0.14)', color: '#FFFFFF' }} />
            </Stack>
          </Box>

          <Box sx={{ position: 'relative', zIndex: 1, display: 'grid', placeItems: 'center' }}>
            <Box sx={{ width: 220, height: 150 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={gauge} dataKey="value" startAngle={180} endAngle={0} cy="90%" innerRadius="72%" outerRadius="100%" stroke="none" cornerRadius={8}>
                    <Cell fill="#A5D8FF" />
                    <Cell fill="rgba(255,255,255,0.16)" />
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            </Box>
            <Typography variant="h3" fontWeight={800} textAlign="center" mt={-6}>
              {score == null ? '—' : `${score}%`}
            </Typography>
            <Typography variant="body2" sx={{ opacity: 0.85 }}>Average control coverage</Typography>
          </Box>
        </Box>

        <Box className="stagger" sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, gap: 2, mb: 3 }}>
          <KpiCard label="Regulations" value={ws.documents.length} tone="sky" />
          <KpiCard label="Open obligations" value={ws.obligations.length} tone="teal" />
          <KpiCard label="Critical gaps" value={criticalGaps} tone="rose" />
          <KpiCard label="Pending approvals" value={pending} tone="mauve" />
        </Box>

        <Box className="stagger" sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' }, gap: 2, mb: 3 }}>
          <Panel title="Regulatory monitoring">
            <Stack direction="row" useFlexGap flexWrap="wrap" spacing={1}>
              {regulatorCounts.length === 0 && <Typography variant="body2" color="text.secondary">No documents yet</Typography>}
              {regulatorCounts.map((r, i) => (
                <Chip
                  key={r.code}
                  label={`${r.code}: ${r.count}`}
                  sx={{ fontWeight: 700, bgcolor: CHIP_TINTS[i % CHIP_TINTS.length], color: '#36393B' }}
                />
              ))}
            </Stack>
          </Panel>

          <Panel title="Gaps by risk">
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Chip label={`${risk.CRITICAL ?? 0} Critical`} color="error" />
              <Chip label={`${risk.HIGH ?? 0} High`} color="error" variant="outlined" />
              <Chip label={`${risk.MEDIUM ?? 0} Medium`} color="warning" />
              <Chip label={`${risk.LOW ?? 0} Low`} color="success" />
            </Stack>
          </Panel>

          <Panel title="Document status">
            <Stack spacing={1}>
              {statusCounts.length === 0 && <Typography variant="body2" color="text.secondary">No documents yet</Typography>}
              {statusCounts.map((s) => (
                <Stack key={s.code} direction="row" justifyContent="space-between" alignItems="center">
                  <StatusChip value={s.code} />
                  <Typography fontWeight={700}>{s.count}</Typography>
                </Stack>
              ))}
            </Stack>
          </Panel>
        </Box>

        <Box className="stagger" sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 2fr' }, gap: 2, mb: 3 }}>
          <Panel title="System health">
            {health ? (
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
                <Chip size="small" label={`Database ${health.database_connected ? 'connected' : 'down'}`} color={health.database_connected ? 'success' : 'error'} />
                <Chip size="small" label={`Blob storage ${health.blob_storage_connected ? 'connected' : 'down'}`} color={health.blob_storage_connected ? 'success' : 'error'} />
                <Chip size="small" label={`LLM ${health.llm_configured ? 'configured' : 'not configured'}`} color={health.llm_configured ? 'success' : 'warning'} />
                <Chip size="small" label={`Watchdog ${health.watchdog_active ? 'active' : 'off'}`} color={health.watchdog_active ? 'success' : 'warning'} />
              </Stack>
            ) : (
              <Typography variant="body2" color="text.secondary">Health endpoint unavailable</Typography>
            )}
          </Panel>

          <Panel title="Recent activity">
            <List dense>
              {ws.audit.length === 0 && <Typography variant="body2" color="text.secondary">No activity yet</Typography>}
              {ws.audit.slice(0, 6).map((a) => (
                <ListItem key={a.id} disableGutters>
                  <Box sx={{ width: 10, height: 10, borderRadius: '50%', mr: 1.5, background: 'linear-gradient(#A5D8FF, #C49799)' }} />
                  <ListItemText primary={`${a.event_type} · ${a.doc_code}`} secondary={fmtDate(a.created_at)} />
                </ListItem>
              ))}
            </List>
          </Panel>
        </Box>

        {criticalGaps > 0 && (
          <Alert
            severity="warning"
            variant="filled"
            sx={{ borderRadius: 4, background: 'linear-gradient(120deg, #C49799, #A87A7C)', color: '#36393B', '& .MuiAlert-icon': { color: '#36393B' } }}
          >
            {criticalGaps} high-risk {criticalGaps === 1 ? 'gap was' : 'gaps were'} found across the regulations in the repository.
          </Alert>
        )}
      </LoadState>
    </>
  );
}
