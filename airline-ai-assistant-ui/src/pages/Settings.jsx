import { useState } from 'react';
import { Button, Card, Chip, List, ListItem, ListItemText, Stack, Tab, Tabs, Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { PageHeader, LoadState, EmptyState, fmtDate } from '../components/common.jsx';
import { useWorkspace, countBy } from '../data/WorkspaceContext.jsx';

const sourceColumns = [
  { field: 'name', headerName: 'Source', width: 160 },
  { field: 'documents', headerName: 'Documents', width: 130 },
  { field: 'lastVerified', headerName: 'Last verified', flex: 1, minWidth: 180 },
];

export default function Settings() {
  const ws = useWorkspace();
  const [tab, setTab] = useState(0);

  const sources = countBy(ws.documents, (d) => d.regulator).map((r) => {
    const docs = ws.documents.filter((d) => d.regulator === r.code);
    const latest = docs.map((d) => d.last_verified_at).filter(Boolean).sort().pop();
    return { id: r.code, name: r.code, documents: r.count, lastVerified: fmtDate(latest) };
  });

  const health = ws.health;

  return (
    <>
      <PageHeader eyebrow="Admin" title="Sources, users & config" subtitle="Regulator sources and platform configuration" />

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Sources" />
        <Tab label="Users & roles" />
        <Tab label="Configuration" />
      </Tabs>

      <LoadState loading={ws.loading} error={ws.error} onRetry={ws.reload}>
        {tab === 0 && (
          <Card>
            {sources.length === 0 ? <EmptyState text="No sources yet." /> : (
              <DataGrid rows={sources} columns={sourceColumns} autoHeight disableRowSelectionOnClick hideFooter />
            )}
          </Card>
        )}

        {tab === 1 && (
          <Card><EmptyState text="The API has no user or role endpoint yet." /></Card>
        )}

        {tab === 2 && (
          <Card sx={{ p: 3 }}>
            {!health ? <EmptyState text="Configuration is unavailable because the health endpoint did not respond." /> : (
              <Stack spacing={2}>
                <List dense disablePadding>
                  <ListItem disableGutters><ListItemText primary="Storage mode" secondary={health.storage_mode} /></ListItem>
                  <ListItem disableGutters><ListItemText primary="Watchdog" secondary={health.watchdog_active ? `Active, every ${health.watchdog_interval_seconds}s` : 'Inactive'} /></ListItem>
                  <ListItem disableGutters><ListItemText primary="LLM" secondary={health.llm_configured ? 'Configured' : 'Not configured'} /></ListItem>
                  <ListItem disableGutters><ListItemText primary="Last health check" secondary={fmtDate(health.timestamp)} /></ListItem>
                </List>
                <Stack direction="row" spacing={1}>
                  <Chip label={health.database_connected ? 'Database connected' : 'Database down'} color={health.database_connected ? 'success' : 'error'} />
                  <Chip label={health.blob_storage_connected ? 'Blob storage connected' : 'Blob storage down'} color={health.blob_storage_connected ? 'success' : 'error'} />
                </Stack>
                <Typography variant="caption" color="text.secondary">Settings are read-only here. Change them on the backend configuration.</Typography>
                <Button variant="outlined" onClick={ws.reload} sx={{ alignSelf: 'flex-start' }}>Refresh</Button>
              </Stack>
            )}
          </Card>
        )}
      </LoadState>
    </>
  );
}
