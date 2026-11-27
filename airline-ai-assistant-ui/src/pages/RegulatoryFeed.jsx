import { useState } from 'react';
import { Alert, Box, Button, Card, CardActions, CardContent, Stack, Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { useNavigate } from 'react-router-dom';
import { PageHeader, StatusChip, LoadState, fmtDate } from '../components/common.jsx';
import { useWorkspace } from '../data/WorkspaceContext.jsx';
import { api } from '../services/api.js';

const columns = [
  { field: 'regulator', headerName: 'Source', width: 110 },
  { field: 'title', headerName: 'Title', flex: 1, minWidth: 260 },
  { field: 'version_tag', headerName: 'Version', width: 100 },
  { field: 'last_verified_at', headerName: 'Last verified', width: 180, valueFormatter: (p) => fmtDate(p.value) },
  { field: 'status', headerName: 'Status', width: 130, renderCell: (p) => <StatusChip value={p.value} /> },
];

export default function RegulatoryFeed() {
  const ws = useWorkspace();
  const navigate = useNavigate();
  const [busyId, setBusyId] = useState(null);
  const [message, setMessage] = useState(null);

  const latest = [...ws.documents]
    .sort((a, b) => new Date(b.updated_at ?? 0) - new Date(a.updated_at ?? 0))
    .slice(0, 2);

  const analyze = async (doc) => {
    setBusyId(doc.id);
    setMessage(null);
    try {
      await api.extractObligations(doc.id);
      setMessage({ severity: 'success', text: `Obligation extraction started for ${doc.doc_code}.` });
      ws.reload();
    } catch (e) {
      setMessage({ severity: 'error', text: e.message });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <PageHeader eyebrow="Regulatory intelligence" title="Regulatory feed" subtitle="Live monitoring of regulator sources" />

      {message && <Alert severity={message.severity} sx={{ mb: 2 }} onClose={() => setMessage(null)}>{message.text}</Alert>}

      <LoadState loading={ws.loading} error={ws.error} onRetry={ws.reload}>
        {latest.length > 0 && (
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' }, gap: 2, mb: 3 }}>
            {latest.map((d) => (
              <Card key={d.id} className="lift">
                <CardContent>
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Typography variant="overline" color="text.secondary">{d.regulator}</Typography>
                    <StatusChip value={d.status} />
                  </Stack>
                  <Typography variant="h6" fontWeight={600}>{d.title}</Typography>
                  <Typography variant="body2" color="text.secondary">Updated {fmtDate(d.updated_at)}</Typography>
                </CardContent>
                <CardActions>
                  <Button size="small" onClick={() => navigate(`/regulations/${d.id}`)}>View</Button>
                  <Button size="small" disabled={busyId === d.id} onClick={() => analyze(d)}>Analyze</Button>
                  <Button size="small" component="a" href={d.source_url} target="_blank" rel="noreferrer" disabled={!d.source_url}>
                    Source
                  </Button>
                </CardActions>
              </Card>
            ))}
          </Box>
        )}

        <Card>
          <DataGrid
            rows={ws.documents}
            columns={columns}
            autoHeight
            disableRowSelectionOnClick
            initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
            pageSizeOptions={[10, 25]}
            onRowClick={(p) => navigate(`/regulations/${p.row.id}`)}
          />
        </Card>
      </LoadState>
    </>
  );
}
