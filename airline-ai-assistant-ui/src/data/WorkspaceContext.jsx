import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api.js';

const WorkspaceContext = createContext(null);

const settled = (r) => (r.status === 'fulfilled' ? r.value : null);

// Loads everything the screens need in one pass. Per-document calls use allSettled,
// so a document that is not ready yet (409) does not break the whole workspace.
async function loadAll() {
  const [docsRes, health, auditRes] = await Promise.all([
    api.listDocuments(),
    api.health().catch(() => null),
    api.auditLogs(100).catch(() => ({ logs: [] })),
  ]);

  const documents = docsRes.documents ?? [];

  const perDoc = await Promise.all(
    documents.map(async (doc) => {
      const [obl, gaps, impact, tasks] = await Promise.allSettled([
        api.documentObligations(doc.doc_code),
        api.gaps(doc.id),
        api.mappingImpact(doc.doc_code),
        api.remediationTasks(doc.id),
      ]);
      return {
        doc,
        obligations: settled(obl)?.obligations ?? [],
        gaps: settled(gaps),
        impacts: settled(impact) ?? [],
        tasks: settled(tasks)?.tasks ?? [],
      };
    })
  );

  return { documents, health, audit: auditRes.logs ?? [], perDoc };
}

export function WorkspaceProvider({ children }) {
  const [state, setState] = useState({ loading: true, error: null, data: null });

  const reload = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    loadAll()
      .then((data) => setState({ loading: false, error: null, data }))
      .catch((err) => setState({ loading: false, error: err.message || 'Could not load data', data: null }));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const value = useMemo(() => {
    const data = state.data;
    const perDoc = data?.perDoc ?? [];

    const obligations = perDoc.flatMap((p) => p.obligations.map((o) => ({ ...o, doc_code: p.doc.doc_code })));
    const impacts = perDoc.flatMap((p) => p.impacts.map((i) => ({ ...i, doc_code: p.doc.doc_code })));
    const gaps = perDoc.flatMap((p) =>
      (p.gaps?.assessments ?? []).map((g) => ({ ...g, doc_code: p.doc.doc_code, document_id: p.doc.id }))
    );
    const tasks = perDoc.flatMap((p) => p.tasks.map((t) => ({ ...t, doc_code: p.doc.doc_code })));

    const gapStats = perDoc.reduce(
      (acc, p) => {
        const s = p.gaps?.stats;
        if (!s) return acc;
        acc.total += s.total ?? 0;
        acc.compliant += s.compliant ?? 0;
        acc.with_gaps += s.with_gaps ?? 0;
        acc.needs_review += s.needs_review ?? 0;
        Object.entries(s.by_risk ?? {}).forEach(([k, v]) => {
          acc.by_risk[k] = (acc.by_risk[k] ?? 0) + v;
        });
        return acc;
      },
      { total: 0, compliant: 0, with_gaps: 0, needs_review: 0, by_risk: {} }
    );

    const complianceScore = gaps.length
      ? Math.round(gaps.reduce((sum, g) => sum + (g.coverage_score ?? 0), 0) / gaps.length)
      : null;

    return {
      loading: state.loading,
      error: state.error,
      reload,
      documents: data?.documents ?? [],
      health: data?.health ?? null,
      audit: data?.audit ?? [],
      perDoc,
      obligations,
      impacts,
      gaps,
      tasks,
      gapStats,
      complianceScore,
    };
  }, [state, reload]);

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error('useWorkspace must be used inside WorkspaceProvider');
  return ctx;
}

// [{ code, count }] for charts and chips
export function countBy(items, keyFn) {
  const m = new Map();
  items.forEach((it) => {
    const k = keyFn(it) ?? 'Unknown';
    m.set(k, (m.get(k) ?? 0) + 1);
  });
  return [...m.entries()].map(([code, count]) => ({ code, count }));
}

// Mapped policy and control assets still waiting for a human decision
export function pendingAssets(impacts) {
  return impacts.flatMap((imp) =>
    [...(imp.policies ?? []), ...(imp.controls ?? [])]
      .filter((a) => a.review_status === 'PROPOSED')
      .map((a) => ({
        ...a,
        key: `${imp.obligation_id}-${a.code}`,
        obligation_id: imp.obligation_id,
        clause: imp.clause,
        doc_code: imp.doc_code,
      }))
  );
}
