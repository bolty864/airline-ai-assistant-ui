import { useState } from 'react';
import { Box, Chip, Dialog, DialogContent, DialogTitle, List, ListItemButton, ListItemText, Stack, Typography, Card } from '@mui/material';
import { PageHeader, LoadState, EmptyState, fmtDate } from '../components/common.jsx';
import { useWorkspace } from '../data/WorkspaceContext.jsx';

const summarise = (details) => {
  if (!details) return '';
  const s = JSON.stringify(details);
  return s.length > 90 ? `${s.slice(0, 90)}…` : s;
};

export default function AuditTrail() {
  const ws = useWorkspace();
  const [type, setType] = useState('All');
  const [selected, setSelected] = useState(null);

  const types = ['All', ...new Set(ws.audit.map((e) => e.event_type).filter(Boolean))];
  const events = ws.audit.filter((e) => type === 'All' || e.event_type === type);

  return (
    <>
      <PageHeader eyebrow="Operations" title="Audit trail" subtitle="Every action recorded by the platform" />

      <LoadState loading={ws.loading} error={ws.error} onRetry={ws.reload}>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" mb={2}>
          {types.map((t) => (
            <Chip key={t} label={t} clickable color={type === t ? 'primary' : 'default'} onClick={() => setType(t)} />
          ))}
        </Stack>

        <Card>
          {events.length === 0 ? <EmptyState text="No audit events yet." /> : (
            <List>
              {events.map((e) => (
                <ListItemButton key={e.id} onClick={() => setSelected(e)} divider>
                  <Box sx={{ width: 170, flexShrink: 0 }}>
                    <Typography variant="body2" color="text.secondary">{fmtDate(e.created_at)}</Typography>
                  </Box>
                  <ListItemText primary={e.event_type} secondary={`${e.doc_code} · ${summarise(e.details)}`} />
                  <Chip size="small" label={e.doc_code} variant="outlined" />
                </ListItemButton>
              ))}
            </List>
          )}
        </Card>
      </LoadState>

      <Dialog open={!!selected} onClose={() => setSelected(null)} fullWidth maxWidth="sm">
        {selected && (
          <>
            <DialogTitle>{selected.event_type}</DialogTitle>
            <DialogContent>
              <Stack spacing={1}>
                <Typography variant="body2"><b>Time:</b> {fmtDate(selected.created_at)}</Typography>
                <Typography variant="body2"><b>Document:</b> {selected.doc_code}</Typography>
                <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap', bgcolor: '#F6F4F5', p: 1.5, borderRadius: 2 }}>
                  {JSON.stringify(selected.details ?? {}, null, 2)}
                </Typography>
              </Stack>
            </DialogContent>
          </>
        )}
      </Dialog>
    </>
  );
}
