import { useState } from 'react';
import { Box, Card, CardActionArea, CardContent, Dialog, DialogContent, DialogTitle, Stack, Typography, Alert } from '@mui/material';
import { PageHeader, StatusChip, LoadState } from '../components/common.jsx';
import { useWorkspace } from '../data/WorkspaceContext.jsx';

const COLUMNS = [
  { key: 'OPEN', title: 'Backlog' },
  { key: 'IN_PROGRESS', title: 'In progress' },
  { key: 'DONE', title: 'Completed' },
];

export default function Tasks() {
  const ws = useWorkspace();
  const [active, setActive] = useState(null);

  return (
    <>
      <PageHeader eyebrow="Remediation" title="Tasks & action plans" subtitle="Remediation backlog generated from change impacts" />

      <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>
        Task status changes are not in the API spec yet, so tasks are read-only here.
      </Alert>

      <LoadState loading={ws.loading} error={ws.error} onRetry={ws.reload}>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' }, gap: 2, alignItems: 'start' }}>
          {COLUMNS.map((col) => {
            const items = ws.tasks.filter((t) => t.status === col.key);
            return (
              <Box key={col.key} sx={{ bgcolor: '#F0ECEE', borderRadius: 2, p: 1.5, minHeight: 300 }}>
                <Stack direction="row" justifyContent="space-between" mb={1.5}>
                  <Typography variant="subtitle2" fontWeight={700}>{col.title}</Typography>
                  <Typography variant="caption" color="text.secondary">{items.length}</Typography>
                </Stack>
                <Stack spacing={1.5}>
                  {items.map((t) => (
                    <Card key={t.id}>
                      <CardActionArea onClick={() => setActive(t)}>
                        <CardContent>
                          <Typography variant="body2" fontWeight={600}>{t.task_name}</Typography>
                          <Typography variant="caption" color="text.secondary" display="block">{t.owner_team ?? 'Unassigned'}</Typography>
                          <Stack direction="row" justifyContent="space-between" alignItems="center" mt={1}>
                            <StatusChip value={t.priority} />
                            <Typography variant="caption">{t.due_days != null ? `Due in ${t.due_days}d` : '—'}</Typography>
                          </Stack>
                        </CardContent>
                      </CardActionArea>
                    </Card>
                  ))}
                </Stack>
              </Box>
            );
          })}
        </Box>
      </LoadState>

      <Dialog open={!!active} onClose={() => setActive(null)} fullWidth maxWidth="sm">
        {active && (
          <>
            <DialogTitle>{active.task_name}</DialogTitle>
            <DialogContent>
              <Stack spacing={1.5}>
                <Typography variant="body2"><b>Document:</b> {active.doc_code}</Typography>
                <Typography variant="body2"><b>Owner:</b> {active.owner_team ?? 'Unassigned'}</Typography>
                <Typography variant="body2"><b>Due:</b> {active.due_days != null ? `In ${active.due_days} days` : '—'}</Typography>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Typography variant="body2"><b>Priority:</b></Typography>
                  <StatusChip value={active.priority} />
                </Stack>
                <Typography variant="body2"><b>Clause:</b> {active.clause_ref ?? '—'}</Typography>
                <Typography variant="body2"><b>Change type:</b> {active.change_type ?? '—'}</Typography>
                <Typography variant="body2"><b>Detail:</b> {active.detail ?? '—'}</Typography>
              </Stack>
            </DialogContent>
          </>
        )}
      </Dialog>
    </>
  );
}
