import { useState } from 'react';
import { Alert, Box, Button, Card, CardActions, CardContent, Stack, Tooltip, Typography } from '@mui/material';
import { PageHeader, StatusChip, LoadState, EmptyState } from '../components/common.jsx';
import { useWorkspace, pendingAssets } from '../data/WorkspaceContext.jsx';
import { api } from '../services/api.js';

export default function Approvals() {
  const ws = useWorkspace();
  const [busyKey, setBusyKey] = useState(null);
  const [message, setMessage] = useState(null);

  const items = pendingAssets(ws.impacts);

  const decide = async (item, status) => {
    setBusyKey(item.key);
    setMessage(null);
    try {
      await api.reviewMapping(item.mapping_id, status);
      setMessage({ severity: 'success', text: `${item.name} marked ${status.toLowerCase()}. Audit evidence captured.` });
      ws.reload();
    } catch (e) {
      setMessage({ severity: 'error', text: e.message });
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <>
      <PageHeader eyebrow="Remediation" title="Compliance review & approval" subtitle="Mapped assets waiting for a human decision" />

      {message && <Alert severity={message.severity} sx={{ mb: 2 }} onClose={() => setMessage(null)}>{message.text}</Alert>}

      <LoadState loading={ws.loading} error={ws.error} onRetry={ws.reload}>
        {items.length === 0 ? (
          <Card><EmptyState text="Nothing is waiting for approval." /></Card>
        ) : (
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' }, gap: 2 }}>
            {items.map((a) => {
              const canAct = a.mapping_id != null;
              const reason = canAct ? '' : 'The mapping ID is missing from the impact response, so this cannot be reviewed yet.';
              return (
                <Card key={a.key}>
                  <CardContent>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
                      <Typography variant="subtitle1" fontWeight={700}>{a.name}</Typography>
                      <StatusChip value={a.review_status} />
                    </Stack>
                    <Typography variant="body2" mb={1}>{a.rationale || 'No rationale returned.'}</Typography>
                    <Stack direction="row" spacing={2} useFlexGap flexWrap="wrap">
                      <Typography variant="caption" color="text.secondary">Document: <b>{a.doc_code}</b></Typography>
                      <Typography variant="caption" color="text.secondary">Clause: <b>{a.clause ?? '—'}</b></Typography>
                      <Typography variant="caption" color="text.secondary">Relevance: <b>{a.relevance ?? '—'}%</b></Typography>
                      <Typography variant="caption" color="text.secondary">Link: <b>{a.link_type}</b></Typography>
                    </Stack>
                  </CardContent>
                  <CardActions>
                    <Tooltip title={reason}>
                      <span>
                        <Button size="small" variant="contained" color="success" disabled={!canAct || busyKey === a.key} onClick={() => decide(a, 'CONFIRMED')}>Approve</Button>
                      </span>
                    </Tooltip>
                    <Tooltip title={reason}>
                      <span>
                        <Button size="small" variant="outlined" color="error" disabled={!canAct || busyKey === a.key} onClick={() => decide(a, 'REJECTED')}>Reject</Button>
                      </span>
                    </Tooltip>
                  </CardActions>
                </Card>
              );
            })}
          </Box>
        )}
      </LoadState>
    </>
  );
}
