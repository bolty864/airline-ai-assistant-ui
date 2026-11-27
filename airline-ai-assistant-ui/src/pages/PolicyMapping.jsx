import { useState } from 'react';
import { Box, Card, Chip, Stack, Tab, Tabs } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import { ReactFlow, Background, Controls } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { PageHeader, Panel, LoadState, EmptyState } from '../components/common.jsx';
import { useWorkspace } from '../data/WorkspaceContext.jsx';

const tableColumns = [
  { field: 'regulation', headerName: 'Regulation', width: 200 },
  { field: 'policy', headerName: 'Policy', flex: 1, minWidth: 220 },
  { field: 'system', headerName: 'System', flex: 1, minWidth: 200 },
  { field: 'control', headerName: 'Control', width: 160 },
];

function buildGraph(impact) {
  const policies = impact.policies ?? [];
  const controls = impact.controls ?? [];
  const systems = impact.systems ?? [];

  const nodes = [
    {
      id: 'reg',
      position: { x: 0, y: 150 },
      data: { label: `${impact.doc_code} / Clause ${impact.clause ?? '—'}` },
      style: { background: '#36393B', color: '#fff', borderRadius: 8, width: 200 },
    },
  ];
  const edges = [];

  policies.forEach((p, i) => {
    const id = `p-${p.code}-${i}`;
    nodes.push({ id, position: { x: 300, y: i * 110 + 40 }, data: { label: `${p.name} (s.${p.section ?? '—'})` }, style: { width: 220, borderRadius: 8 } });
    edges.push({ id: `e-${id}`, source: 'reg', target: id, label: p.link_type });
  });

  controls.forEach((c, i) => {
    const id = `c-${c.code}-${i}`;
    nodes.push({ id, position: { x: 620, y: i * 110 + 40 }, data: { label: `${c.code} ${c.name}` }, style: { width: 200, borderRadius: 8 } });
    edges.push({ id: `e-${id}`, source: 'reg', target: id, label: c.link_type });
  });

  systems.forEach((s, i) => {
    const id = `s-${s.code}-${i}`;
    const y = (controls.length + i) * 110 + 40;
    nodes.push({ id, position: { x: 620, y }, data: { label: s.name }, style: { width: 200, borderRadius: 8, background: '#E6F4FA' } });
    edges.push({ id: `e-${id}`, source: 'reg', target: id, label: s.link_type });
  });

  return { nodes, edges };
}

export default function PolicyMapping() {
  const ws = useWorkspace();
  const [tab, setTab] = useState(0);
  const [selectedId, setSelectedId] = useState(null);

  const impacts = ws.impacts;
  const impact = impacts.find((m) => m.obligation_id === selectedId) ?? impacts[0];

  const rows = impacts.map((m) => ({
    id: m.obligation_id,
    regulation: `${m.doc_code} · Clause ${m.clause ?? '—'}`,
    policy: (m.policies ?? []).map((p) => p.name).join(', ') || '—',
    system: (m.systems ?? []).map((s) => s.name).join(', ') || '—',
    control: (m.controls ?? []).map((c) => c.code).join(', ') || '—',
  }));

  return (
    <>
      <PageHeader eyebrow="Compliance analysis" title="Policy mapping" subtitle="Relation between regulation obligations and airline assets" />

      <LoadState loading={ws.loading} error={ws.error} onRetry={ws.reload}>
        {impacts.length === 0 ? (
          <Card><EmptyState text="No mapped obligations yet. Run mapping from the Agent 3 pipeline." /></Card>
        ) : (
          <>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" mb={2}>
              {impacts.map((m) => (
                <Chip
                  key={m.obligation_id}
                  label={`${m.doc_code} · ${m.clause ?? '—'}`}
                  clickable
                  color={m.obligation_id === impact.obligation_id ? 'primary' : 'default'}
                  onClick={() => setSelectedId(m.obligation_id)}
                />
              ))}
            </Stack>

            <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
              <Tab label="Graph view" />
              <Tab label="Tabular view" />
            </Tabs>

            {tab === 0 && (
              <Panel>
                <Box sx={{ height: 420 }}>
                  <ReactFlow {...buildGraph(impact)} fitView proOptions={{ hideAttribution: true }}>
                    <Background />
                    <Controls />
                  </ReactFlow>
                </Box>
              </Panel>
            )}

            {tab === 1 && (
              <Card>
                <DataGrid rows={rows} columns={tableColumns} autoHeight disableRowSelectionOnClick hideFooter />
              </Card>
            )}
          </>
        )}
      </LoadState>
    </>
  );
}
