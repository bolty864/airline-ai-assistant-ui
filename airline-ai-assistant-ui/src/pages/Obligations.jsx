import { useState } from 'react';
import { Card, Chip, Divider, Drawer, Stack, Typography, Box } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { PageHeader, StatusChip, LoadState, fmtDate } from '../components/common.jsx';
import { useWorkspace } from '../data/WorkspaceContext.jsx';

const SEVERITIES = ['HIGH', 'MEDIUM', 'LOW'];

const columns = [
  { field: 'doc_code', headerName: 'Document', width: 170 },
  { field: 'clause_ref', headerName: 'Clause', width: 90 },
  { field: 'obligation_text', headerName: 'Requirement', flex: 1, minWidth: 300 },
  { field: 'owner_function', headerName: 'Owner', width: 180 },
  {
    field: 'confidence_score', headerName: 'Confidence', width: 120,
    valueFormatter: (p) => (p.value == null ? '—' : `${p.value}%`),
  },
  { field: 'severity', headerName: 'Severity', width: 110, renderCell: (p) => <StatusChip value={p.value} /> },
  { field: 'mapping_status', headerName: 'Mapping', width: 130, renderCell: (p) => <StatusChip value={p.value} /> },
];

export default function Obligations() {
  const ws = useWorkspace();
  const [severity, setSeverity] = useState(SEVERITIES);
  const [selected, setSelected] = useState(null);

  const rows = ws.obligations.filter((o) => !o.severity || severity.includes(o.severity));

  const toggle = (s) =>
    setSeverity((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));

  return (
    <>
      <PageHeader eyebrow="Compliance analysis" title="Obligations" subtitle="Requirements extracted from regulations" />

      <Stack direction="row" spacing={1} mb={2}>
        {SEVERITIES.map((s) => (
          <Chip key={s} label={s} clickable color={severity.includes(s) ? 'primary' : 'default'} onClick={() => toggle(s)} />
        ))}
      </Stack>

      <LoadState loading={ws.loading} error={ws.error} onRetry={ws.reload}>
        <Card>
          <DataGrid
            rows={rows}
            columns={columns}
            autoHeight
            disableRowSelectionOnClick
            initialState={{ pagination: { paginationModel: { pageSize: 10 } } }}
            pageSizeOptions={[10, 25]}
            onRowClick={(p) => setSelected(p.row)}
          />
        </Card>
      </LoadState>

      <Drawer anchor="right" open={!!selected} onClose={() => setSelected(null)} slotProps={{ paper: { sx: { width: 460, p: 3 } } }}>
        {selected && (
          <Stack spacing={2}>
            <Typography variant="overline" color="text.secondary">{selected.doc_code} · Clause {selected.clause_ref ?? '—'}</Typography>
            <Typography variant="h6" fontWeight={700}>{selected.obligation_text}</Typography>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <StatusChip value={selected.severity} />
              <StatusChip value={selected.mapping_status} />
              <Chip size="small" label={selected.confidence_score == null ? 'Confidence n/a' : `${selected.confidence_score}% confidence`} variant="outlined" />
            </Stack>
            <Divider />
            <Box>
              <Typography variant="subtitle2" fontWeight={600}>Citation</Typography>
              <Typography variant="body2" sx={{ fontStyle: 'italic' }}>{selected.citation ?? '—'}</Typography>
            </Box>
            <Box>
              <Typography variant="subtitle2" fontWeight={600}>Type</Typography>
              <Typography variant="body2">{selected.obligation_type ?? '—'}</Typography>
            </Box>
            <Box>
              <Typography variant="subtitle2" fontWeight={600}>Owner</Typography>
              <Typography variant="body2">{selected.owner_function ?? '—'}</Typography>
            </Box>
            <Box>
              <Typography variant="subtitle2" fontWeight={600}>Target system</Typography>
              <Typography variant="body2">{selected.target_system ?? '—'}</Typography>
            </Box>
            <Box>
              <Typography variant="subtitle2" fontWeight={600}>Extracted</Typography>
              <Typography variant="body2">{fmtDate(selected.created_at)}</Typography>
            </Box>
          </Stack>
        )}
      </Drawer>
    </>
  );
}
