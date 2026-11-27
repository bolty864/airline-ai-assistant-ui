import { useState } from 'react';
import { Box, Chip, List, ListItemButton, ListItemText, Paper, Stack, TextField, Typography, Card } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { useNavigate, useParams } from 'react-router-dom';
import { PageHeader, Panel, StatusChip, LoadState, EmptyState } from '../components/common.jsx';
import { useWorkspace, countBy } from '../data/WorkspaceContext.jsx';

const columns = [
  { field: 'doc_code', headerName: 'Document', flex: 1, minWidth: 180 },
  { field: 'regulator', headerName: 'Source', width: 100 },
  { field: 'version_tag', headerName: 'Version', width: 90 },
  { field: 'status', headerName: 'Status', width: 120, renderCell: (p) => <StatusChip value={p.value} /> },
];

export default function RegulationRepository() {
  const { id } = useParams();
  const navigate = useNavigate();
  const ws = useWorkspace();
  const [query, setQuery] = useState('');
  const [regs, setRegs] = useState(null); // null = all regulators
  const [activeId, setActiveId] = useState(null);

  const regulators = countBy(ws.documents, (d) => d.regulator).map((r) => r.code);
  const activeRegs = regs ?? regulators;

  const selected = ws.documents.find((d) => String(d.id) === id) ?? ws.documents[0];
  const clauses = ws.perDoc.find((p) => p.doc.id === selected?.id)?.obligations ?? [];
  const activeClause = activeId ?? clauses[0]?.id;

  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const rows = ws.documents.filter((d) => {
    const hay = `${d.title ?? ''} ${d.doc_code ?? ''}`.toLowerCase();
    const matchesQuery = words.length === 0 || words.some((w) => hay.includes(w));
    return matchesQuery && activeRegs.includes(d.regulator);
  });

  const toggleReg = (code) => {
    const current = regs ?? regulators;
    setRegs(current.includes(code) ? current.filter((r) => r !== code) : [...current, code]);
  };

  return (
    <>
      <PageHeader eyebrow="Regulatory intelligence" title="Regulations repository" subtitle="All regulatory documents and their extracted clauses" />

      <LoadState loading={ws.loading} error={ws.error} onRetry={ws.reload}>
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '5fr 7fr' }, gap: 2 }}>
          <Stack spacing={2}>
            <TextField size="small" label="Search" value={query} onChange={(e) => setQuery(e.target.value)} />
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              {regulators.map((r) => (
                <Chip
                  key={r}
                  label={r}
                  clickable
                  color={activeRegs.includes(r) ? 'primary' : 'default'}
                  variant={activeRegs.includes(r) ? 'filled' : 'outlined'}
                  onClick={() => toggleReg(r)}
                />
              ))}
            </Stack>
            <Card>
              <DataGrid
                rows={rows}
                columns={columns}
                autoHeight
                disableRowSelectionOnClick
                onRowClick={(p) => navigate(`/regulations/${p.row.id}`)}
              />
            </Card>
          </Stack>

          <Panel title={selected ? `Document viewer: ${selected.filename}` : 'Document viewer'}>
            {!selected ? (
              <EmptyState text="Select a regulation to view its clauses." />
            ) : (
              <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '3fr 2fr' }, gap: 2 }}>
                <Paper variant="outlined" sx={{ p: 2, minHeight: 320, bgcolor: '#FBFAFB' }}>
                  <Typography variant="caption" color="text.secondary">Extracted citations</Typography>
                  {clauses.length === 0 && <EmptyState text="No obligations extracted yet for this document." />}
                  {clauses.map((c) => (
                    <Typography
                      key={c.id}
                      variant="body2"
                      sx={{
                        mt: 1.5,
                        p: 1,
                        borderRadius: 1,
                        bgcolor: c.id === activeClause ? '#A5D8FF55' : 'transparent',
                        transition: 'background-color 0.3s',
                      }}
                    >
                      <b>{c.clause_ref ?? '—'}</b> {c.citation ?? c.obligation_text}
                    </Typography>
                  ))}
                </Paper>

                <Box>
                  <Typography variant="subtitle2" fontWeight={600} mb={1}>Clauses</Typography>
                  <List dense disablePadding>
                    {clauses.map((c) => (
                      <ListItemButton key={c.id} selected={c.id === activeClause} onClick={() => setActiveId(c.id)} sx={{ borderRadius: 1 }}>
                        <ListItemText
                          primary={`Clause ${c.clause_ref ?? '—'}`}
                          secondary={c.obligation_text}
                          secondaryTypographyProps={{ noWrap: true }}
                        />
                      </ListItemButton>
                    ))}
                  </List>
                </Box>
              </Box>
            )}
          </Panel>
        </Box>
      </LoadState>
    </>
  );
}
