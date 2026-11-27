import { Alert, Box, Card, CardContent, Stack, Typography } from '@mui/material';
import { PageHeader, Panel, LoadState, EmptyState } from '../components/common.jsx';
import { useWorkspace } from '../data/WorkspaceContext.jsx';

export default function PolicyDrafts() {
  const ws = useWorkspace();

  // Current policy provisions taken from the mapping impact data
  const provisions = [];
  const seen = new Set();
  ws.impacts.forEach((imp) => {
    (imp.policies ?? []).forEach((p) => {
      const key = `${p.code}-${p.section}`;
      if (seen.has(key)) return;
      seen.add(key);
      provisions.push({ ...p, key, doc_code: imp.doc_code, clause: imp.clause });
    });
  });

  return (
    <>
      <PageHeader eyebrow="Remediation" title="AI policy drafts" subtitle="Current policy text linked to regulation obligations" />

      <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>
        The API does not yet expose a draft endpoint, so AI drafts cannot be shown. The current provisions below come from the mapping data.
      </Alert>

      <LoadState loading={ws.loading} error={ws.error} onRetry={ws.reload}>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '320px 1fr' }, gap: 2 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle2" fontWeight={700} mb={1}>Linked provisions</Typography>
              {provisions.length === 0 && <EmptyState text="No policy provisions linked yet." />}
              <Stack spacing={1}>
                {provisions.map((p) => (
                  <Box key={p.key} sx={{ p: 1.5, borderRadius: 2, bgcolor: '#F6F4F5' }}>
                    <Typography variant="body2" fontWeight={700}>{p.name}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      s.{p.section ?? '—'} · {p.heading ?? ''} · {p.doc_code}
                    </Typography>
                  </Box>
                ))}
              </Stack>
            </CardContent>
          </Card>

          <Panel title="Current provision">
            {provisions.length === 0 ? (
              <EmptyState text="Select a provision once mapping is available." />
            ) : (
              <Stack spacing={2}>
                {provisions.map((p) => (
                  <Box key={p.key} sx={{ p: 2, borderRadius: 2, border: '1px solid #E3DDE0', bgcolor: '#FFFFFF' }}>
                    <Typography variant="overline" color="text.secondary">{p.name} · s.{p.section ?? '—'}</Typography>
                    <Typography variant="body2">{p.current_provision || 'No provision text returned.'}</Typography>
                    <Typography variant="caption" color="text.secondary">Rationale: {p.rationale ?? '—'}</Typography>
                  </Box>
                ))}
              </Stack>
            )}
          </Panel>
        </Box>
      </LoadState>
    </>
  );
}
