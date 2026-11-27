import { Box, Button, Card, CardActions, CardContent, LinearProgress, Stack, Typography } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { PageHeader, StatusChip, LoadState, EmptyState } from '../components/common.jsx';
import { useWorkspace } from '../data/WorkspaceContext.jsx';

const RISK_BORDER = { CRITICAL: '#8E4F55', HIGH: '#8E4F55', MEDIUM: '#C49799', LOW: '#4E7D84' };

export default function GapAnalysis() {
  const ws = useWorkspace();
  const navigate = useNavigate();

  const stats = ws.gapStats;
  const summary = [
    { label: 'Compliant', value: stats.compliant, color: '#4E7D84' },
    { label: 'With gaps', value: stats.with_gaps, color: '#C49799' },
    { label: 'Needs review', value: stats.needs_review, color: '#8E4F55' },
  ];

  const gaps = ws.gaps
    .filter((g) => g.gap_type !== 'No Gap')
    .sort((a, b) => (b.risk_score ?? 0) - (a.risk_score ?? 0));

  return (
    <>
      <PageHeader eyebrow="Compliance analysis" title="Gap analysis" subtitle="Where existing policies and controls fall short of obligations" />

      <LoadState loading={ws.loading} error={ws.error} onRetry={ws.reload}>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' }, gap: 2, mb: 3 }}>
          {summary.map((s) => (
            <Card key={s.label} sx={{ borderLeft: `6px solid ${s.color}` }}>
              <CardContent>
                <Typography variant="overline" color="text.secondary">{s.label}</Typography>
                <Typography variant="h4" fontWeight={700}>{s.value}</Typography>
              </CardContent>
            </Card>
          ))}
        </Box>

        {gaps.length === 0 ? (
          <Card><EmptyState text="No gaps found. Run gap analysis on a document to see results." /></Card>
        ) : (
          <Stack spacing={2}>
            {gaps.map((g) => (
              <Card key={g.id} sx={{ borderLeft: `6px solid ${RISK_BORDER[g.risk_rating] ?? '#BFB6BB'}` }}>
                <CardContent>
                  <Stack direction="row" spacing={1} alignItems="center" mb={1} useFlexGap flexWrap="wrap">
                    <Typography variant="subtitle1" fontWeight={700}>{g.doc_code} · Clause {g.clause_ref ?? '—'}</Typography>
                    <StatusChip value={g.risk_rating} />
                    <Typography variant="caption" color="text.secondary">{g.gap_type}</Typography>
                    {g.needs_review && <StatusChip value="NEEDS_REVIEW" />}
                  </Stack>
                  <Typography variant="body2"><b>Requirement:</b> {g.obligation_text}</Typography>
                  <Typography variant="body2" color="text.secondary" mt={1}>{g.observation}</Typography>
                  <Typography variant="body2" mt={1}><b>Recommendation:</b> {g.recommendation}</Typography>
                  <Box mt={1.5}>
                    <Typography variant="caption" color="text.secondary">Coverage {g.coverage_score}%</Typography>
                    <LinearProgress variant="determinate" value={g.coverage_score ?? 0} sx={{ height: 6, borderRadius: 3 }} />
                  </Box>
                </CardContent>
                <CardActions>
                  <Button size="small" variant="outlined" onClick={() => navigate('/mapping')}>View mapping</Button>
                  <Button size="small" variant="outlined" onClick={() => navigate('/tasks')}>Tasks</Button>
                  <Button size="small" variant="contained" onClick={() => navigate('/approvals')}>Approvals</Button>
                </CardActions>
              </Card>
            ))}
          </Stack>
        )}
      </LoadState>
    </>
  );
}
