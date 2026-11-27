// Thin client for the AeroComply API. Base URL comes from VITE_API_BASE_URL.
const BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function toMessage(data, res) {
  if (typeof data?.detail === 'string') return data.detail;
  if (Array.isArray(data?.detail)) return data.detail.map((d) => d.msg).join('; ');
  return res.statusText || 'Request failed';
}

async function request(path, { method = 'GET', body } = {}) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, 'network_error', `Cannot reach the API at ${BASE}`);
  }

  let data = null;
  try {
    data = await res.json();
  } catch {
    // empty or non-JSON body
  }

  if (!res.ok) {
    throw new ApiError(res.status, data?.error ?? `http_${res.status}`, toMessage(data, res));
  }
  return data;
}

function query(params) {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
}

export const api = {
  health: () => request('/api/health'),
  listDocuments: () => request('/api/documents'),
  documentObligations: (docCode) => request(`/api/documents/${encodeURIComponent(docCode)}/obligations`),
  extractObligations: (documentId) => request(`/api/obligations/extract/${documentId}?run_in_background=true`, { method: 'POST' }),
  auditLogs: (limit = 100, docCode) => request(`/api/audit-logs${query({ limit, doc_code: docCode })}`),
  mappingImpact: (docCode) => request(`/api/mapping/impact/${encodeURIComponent(docCode)}`),
  reviewMapping: (mappingId, reviewStatus) =>
    request(`/api/mapping/mappings/${mappingId}`, { method: 'PATCH', body: { review_status: reviewStatus } }),
  gaps: (documentId) => request(`/api/gaps/${documentId}`),
  remediationTasks: (documentId) => request(`/api/remediation-tasks/${documentId}`),
  watchdogScan: () => request('/api/watchdog/scan', { method: 'POST' }),
  simulateDelete: (docCode) => request('/api/demo/simulate-delete', { method: 'POST', body: { doc_code: docCode } }),
};
