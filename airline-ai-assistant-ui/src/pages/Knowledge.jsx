import { useState } from 'react';
import { Alert, Card, Tab, Tabs } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { PageHeader, StatusChip, LoadState, EmptyState } from '../components/common.jsx';
import { useWorkspace } from '../data/WorkspaceContext.jsx';

const policyColumns = [
  { field: 'code', headerName: 'Code', width: 120 },
  { field: 'name', headerName: 'Name', flex: 1, minWidth: 220 },
  { field: 'sections', headerName: 'Sections linked', width: 170 },
  { field: 'links', headerName: 'Obligations linked', width: 170 },
];

const controlColumns = [
  { field: 'code', headerName: 'Control', width: 120 },
  { field: 'name', headerName: 'Name', flex: 1, minWidth: 220 },
  { field: 'links', headerName: 'Obligations linked', width: 170 },
  { field: 'relevance', headerName: 'Best relevance', width: 150, valueFormatter: (p) => (p.value == null ? '—' : `${p.value}%`) },
  { field: 'review_status', headerName: 'Review', width: 130, renderCell: (p) => <StatusChip value={p.value} /> },
];

function aggregate(impacts, listKey) {
  const map = new Map();
  impacts.forEach((imp) => {
    (imp[listKey] ?? []).forEach((a) => {
      const row = map.get(a.code) ?? { id: a.code, code: a.code, name: a.name, sections: new Set(), links: 0, relevance: null, review_status: null };
      row.links += 1;
      if (a.section) row.sections.add(a.section);
      row.relevance = Math.max(row.relevance ?? 0, a.relevance ?? 0) || row.relevance;
      row.review_status = row.review_status ?? a.review_status ?? null;
      map.set(a.code, row);
    });
  });
  return [...map.values()].map((r) => ({ ...r, sections: [...r.sections].join(', ') || '—' }));
}

export default function Knowledge() {
  const ws = useWorkspace();
  const [tab, setTab] = useState(0);

  const policies = aggregate(ws.impacts, 'policies');
  const controls = aggregate(ws.impacts, 'controls');

  return (
    <>
      <PageHeader eyebrow="Knowledge hub" title="Policies, SOPs & controls" subtitle="Enterprise repository as seen through obligation mappings" />

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Policies" />
        <Tab label="SOPs" />
        <Tab label="Controls" />
        <Tab label="Version history" />
      </Tabs>

      <LoadState loading={ws.loading} error={ws.error} onRetry={ws.reload}>
        {tab === 0 && (
          <Card>
            {policies.length === 0 ? <EmptyState text="No policies linked to obligations yet." /> : (
              <DataGrid rows={policies} columns={policyColumns} autoHeight disableRowSelectionOnClick hideFooter />
            )}
          </Card>
        )}
        {tab === 1 && (
          <Card><EmptyState text="The API has no SOP listing endpoint yet." /></Card>
        )}
        {tab === 2 && (
          <Card>
            {controls.length === 0 ? <EmptyState text="No controls linked to obligations yet." /> : (
              <DataGrid rows={controls} columns={controlColumns} autoHeight disableRowSelectionOnClick hideFooter />
            )}
          </Card>
        )}
        {tab === 3 && (
          <Alert severity="info" variant="outlined">The API has no version history endpoint yet.</Alert>
        )}
      </LoadState>
    </>
  );
}
