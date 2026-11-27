// Dummy data. Shapes mirror the AeroComply API schemas (DocumentOut, ObligationOut,
// GapAssessmentOut, ChangeImpactOut, RemediationTaskOut, ...) so the API can replace
// these arrays without touching the components.

export const kpis = {
  regulations: 45,
  openObligations: 21,
  criticalGaps: 3,
  pendingApprovals: 4,
  publishedUpdates: 17,
  complianceScore: 92,
};

export const regulatorCounts = [
  { code: 'DGCA', count: 12 },
  { code: 'BCAS', count: 8 },
  { code: 'ICAO', count: 14 },
  { code: 'CERT-IN', count: 6 },
  { code: 'DPDP', count: 5 },
];

export const gapSummary = { compliant: 23, partial: 11, nonCompliant: 3 };
export const gapSeverityCounts = { high: 3, medium: 11, low: 7 };
export const policyStatus = { pendingReview: 4, approved: 17, drafts: 9 };

export const activityTimeline = [
  { time: '09:10', text: 'DGCA circular detected' },
  { time: '09:12', text: 'Obligations extracted' },
  { time: '09:14', text: 'Gap identified' },
  { time: '09:15', text: 'Policy draft generated' },
  { time: '09:20', text: 'Approved by compliance officer' },
  { time: '09:21', text: 'Version 2 published' },
];

// DocumentOut (UI status: New / Processing / Analyzed / Mapped / Published)
export const documents = [
  { id: 1, doc_code: 'DGCA-CAR-SEC5-X', filename: 'DGCA_CAR_SEC5_SERIES_X.pdf', regulator: 'DGCA', title: 'CAR Sec 5 Series X: Passenger API data', version_tag: 'v1', status: 'Analyzed', impact: 'HIGH', detected: '5 mins ago', obligation_count: 5 },
  { id: 2, doc_code: 'DGCA-CAR-API-RET', filename: 'DGCA_CAR_API_Retention.pdf', regulator: 'DGCA', title: 'API retention requirements', version_tag: 'v2', status: 'New', impact: 'MEDIUM', detected: 'Today', obligation_count: 0 },
  { id: 3, doc_code: 'BCAS-SD-2026-07', filename: 'BCAS_SD_2026_07.pdf', regulator: 'BCAS', title: 'Security directive on airport access', version_tag: 'v1', status: 'Processing', impact: 'MEDIUM', detected: 'Today', obligation_count: 0 },
  { id: 4, doc_code: 'ICAO-ANX17-AMD', filename: 'ICAO_Annex17_Amd.pdf', regulator: 'ICAO', title: 'Annex 17 amendment (security)', version_tag: 'v3', status: 'Mapped', impact: 'MEDIUM', detected: '1 day ago', obligation_count: 7 },
  { id: 5, doc_code: 'CERTIN-ADV-26-14', filename: 'CERTIN_ADV_2026_14.pdf', regulator: 'CERT-IN', title: 'Cyber incident reporting advisory', version_tag: 'v1', status: 'Published', impact: 'LOW', detected: '2 days ago', obligation_count: 3 },
  { id: 6, doc_code: 'DPDP-NOTIF-26-03', filename: 'DPDP_Notif_2026_03.pdf', regulator: 'DPDP', title: 'Passport data handling notification', version_tag: 'v1', status: 'Analyzed', impact: 'HIGH', detected: '3 days ago', obligation_count: 4 },
  { id: 7, doc_code: 'IATA-SSR-2026', filename: 'IATA_SSR_Guideline.pdf', regulator: 'IATA', title: 'Special service request handling', version_tag: 'v1', status: 'Published', impact: 'LOW', detected: '1 week ago', obligation_count: 2 },
];

// Clauses shown in the split-screen document viewer
export const regulationClauses = [
  { clause: '4.1', text: 'This section applies to all passenger data collected for advance passenger information (API) submissions.' },
  { clause: '4.2', text: 'Passenger API records shall be retained for minimum 5 years.' },
  { clause: '4.5', text: 'Failures in API transmission shall be reported to the Authority within 24 hours.' },
  { clause: '6.1', text: 'Passport and visa data shall be encrypted at rest.' },
];

// ObligationOut (Agent 2)
export const obligations = [
  { id: 101, doc_code: 'DGCA-CAR-SEC5-X', clause_ref: '4.2', obligation_text: 'Retain passenger API records for a minimum of 5 years', obligation_type: 'RETENTION', owner_function: 'Data Governance', severity: 'HIGH', confidence_score: 95, due_days: 30, citation: 'Passenger API records shall be retained for minimum 5 years.', target_system: 'APIS Scheduler', mapping_status: 'MAPPED' },
  { id: 102, doc_code: 'DGCA-CAR-SEC5-X', clause_ref: '4.5', obligation_text: 'Report API transmission failures to DGCA within 24 hours', obligation_type: 'REPORTING', owner_function: 'Flight Operations', severity: 'HIGH', confidence_score: 91, due_days: 30, citation: 'Failures in API transmission shall be reported to the Authority within 24 hours.', target_system: 'Departure Control System', mapping_status: 'MAPPED' },
  { id: 103, doc_code: 'DPDP-NOTIF-26-03', clause_ref: '6.1', obligation_text: 'Encrypt stored passport data using AES-256', obligation_type: 'SECURITY', owner_function: 'Information Security', severity: 'HIGH', confidence_score: 92, due_days: 45, citation: 'Passport and visa data shall be encrypted at rest.', target_system: 'Data Warehouse', mapping_status: 'NEEDS_REVIEW' },
  { id: 104, doc_code: 'BCAS-SD-2026-07', clause_ref: '6.3', obligation_text: 'Review access to passenger data every quarter', obligation_type: 'ACCESS', owner_function: 'Information Security', severity: 'MEDIUM', confidence_score: 88, due_days: 60, citation: 'Access to passenger data shall be reviewed quarterly.', target_system: 'Customer Portal', mapping_status: 'MAPPED' },
  { id: 105, doc_code: 'DPDP-NOTIF-26-03', clause_ref: '3.1', obligation_text: 'Share passport copies only through approved channels', obligation_type: 'DATA_HANDLING', owner_function: 'Data Governance', severity: 'MEDIUM', confidence_score: 84, due_days: 60, citation: 'Passport copies shall be shared only through approved channels.', target_system: 'SharePoint', mapping_status: 'PENDING' },
  { id: 106, doc_code: 'DPDP-NOTIF-26-03', clause_ref: '2.7', obligation_text: 'Appoint a named data protection officer', obligation_type: 'GOVERNANCE', owner_function: 'Legal', severity: 'LOW', confidence_score: 80, due_days: 90, citation: 'Each data fiduciary shall appoint a named data protection officer.', target_system: 'Governance Register', mapping_status: 'UNMAPPED' },
];

// Shown in the Obligation drawer (AI interpretation, reasons, owner suggestion, evidence)
export const obligationExplain = {
  101: {
    interpretation: 'Passenger API records must be kept for at least 5 years. The current policy keeps them for 3 years, so the retention period must be extended.',
    reasons: ['Clause 4.2 sets a 5-year minimum', 'Passenger Data Policy s.5.3 states 3 years', 'APIS Scheduler purges records at 3 years'],
    ownerSuggestion: 'Data Governance (policy), IT Operations (APIS Scheduler configuration)',
    evidence: ['Clause 4.2, DGCA CAR Sec 5 Series X', 'Policy PDP-2.0 s.5.3', 'Control CTRL-001 APIS Data Retention'],
  },
};

// Agent 3 mapping impact (ObligationImpact + Asset shape)
export const mappingImpacts = [
  {
    obligation_id: 101, clause: '4.2', severity: 'HIGH', mapping_status: 'MAPPED',
    policies: [{ code: 'PDP-2.0', name: 'Passenger Data Policy', section: '5.3', heading: 'Retention', link_type: 'DIRECT', relevance: 96, current_provision: 'Passenger records retained for 3 years.', review_status: 'PROPOSED' }],
    controls: [{ code: 'CTRL-001', name: 'APIS Data Retention', link_type: 'DIRECT', relevance: 94, review_status: 'PROPOSED' }],
    systems: [{ code: 'SYS-APIS', name: 'APIS Scheduler', link_type: 'DIRECT', relevance: 90 }, { code: 'SYS-DWH', name: 'Data Warehouse', link_type: 'SUPPORTING', relevance: 62 }],
  },
  {
    obligation_id: 102, clause: '4.5', severity: 'HIGH', mapping_status: 'MAPPED',
    policies: [{ code: 'CYB-1.4', name: 'Cyber Security Policy', section: '7.2', heading: 'Incident reporting', link_type: 'DIRECT', relevance: 88, current_provision: 'Incidents are reported internally within 72 hours.', review_status: 'CONFIRMED' }],
    controls: [],
    systems: [{ code: 'SYS-DCS', name: 'Departure Control System', link_type: 'DIRECT', relevance: 85 }],
  },
  {
    obligation_id: 103, clause: '6.1', severity: 'HIGH', mapping_status: 'NEEDS_REVIEW',
    policies: [{ code: 'CYB-1.4', name: 'Cyber Security Policy', section: '4.1', heading: 'Encryption', link_type: 'SUPPORTING', relevance: 70, current_provision: 'Sensitive data should be encrypted where practical.', review_status: 'PROPOSED' }],
    controls: [{ code: 'CTRL-002', name: 'Encryption Control', link_type: 'DIRECT', relevance: 93, review_status: 'CONFIRMED' }],
    systems: [{ code: 'SYS-DWH', name: 'Data Warehouse', link_type: 'DIRECT', relevance: 89 }],
  },
];

// GapAssessmentOut (Agent 4)
export const gapAssessments = [
  { id: 1, obligation_id: 101, clause_ref: '4.2', obligation_text: 'Retain passenger API records for a minimum of 5 years', gap_type: 'Retention Mismatch', risk_rating: 'HIGH', risk_score: 88, coverage_score: 40, required: 'Retain for 5 years', current: 'Retain for 3 years', impact: 'Passenger Data Policy', observation: 'Policy retains records for 3 years; the regulation requires 5.', recommendation: 'Raise retention to 5 years in PDP-2.0 s.5.3 and CTRL-001.', confidence_score: 0.95, owner_function: 'Data Governance' },
  { id: 2, obligation_id: 102, clause_ref: '4.5', obligation_text: 'Report API transmission failures to DGCA within 24 hours', gap_type: 'Missing Procedure', risk_rating: 'HIGH', risk_score: 81, coverage_score: 55, required: 'Report to regulator within 24 hours', current: 'Internal reporting only, 72 hours', impact: 'Cyber Security Policy', observation: 'Incident reporting covers internal escalation only, with no regulator deadline.', recommendation: 'Add a 24-hour regulator notification step to the API incident SOP.', confidence_score: 0.91, owner_function: 'Flight Operations' },
  { id: 3, obligation_id: 103, clause_ref: '6.1', obligation_text: 'Encrypt stored passport data using AES-256', gap_type: 'Missing Control', risk_rating: 'HIGH', risk_score: 79, coverage_score: 35, required: 'AES-256 encryption at rest', current: 'No documented control for passport data', impact: 'Cyber Security Policy', observation: 'No documented AES-256 control covers passport data at rest.', recommendation: 'Create CTRL-004 for AES-256 encryption at rest and link it to the Data Warehouse.', confidence_score: 0.84, owner_function: 'Information Security' },
  { id: 4, obligation_id: 105, clause_ref: '3.1', obligation_text: 'Share passport copies only through approved channels', gap_type: 'Partial Coverage', risk_rating: 'MEDIUM', risk_score: 58, coverage_score: 60, required: 'Approved channels only', current: 'SharePoint sharing allowed without restriction', impact: 'Data Handling SOP', observation: 'Sharing is allowed on SharePoint without channel restrictions.', recommendation: 'Restrict passport copy sharing to approved channels in SOP-API-01.', confidence_score: 0.78, owner_function: 'Data Governance' },
];

// AI policy drafts. segments: unchanged text {t}, removed {del}, added {add}
export const drafts = [
  {
    id: 'D-07', title: 'Passenger Data Policy: s.5.3 Retention', clause: '4.2', source: 'DGCA CAR Sec 5 Series X', status: 'Pending review',
    segments: [{ t: 'Passenger records ' }, { t: 'retained for ' }, { del: '3 years' }, { add: '5 years as required under DGCA CAR Sec 5 Series X, Clause 4.2' }, { t: '.' }],
  },
  {
    id: 'D-08', title: 'SOP API Processing: incident escalation', clause: '4.5', source: 'DGCA CAR Sec 5 Series X', status: 'Draft',
    segments: [{ t: 'Incidents affecting API transmission are escalated internally. ' }, { add: 'The regulator is notified within 24 hours of a confirmed failure. ' }, { t: 'Each notification is logged in the audit trail.' }],
  },
];

// RemediationTaskOut. status: OPEN / IN_PROGRESS / REVIEW (UI-only) / DONE
export const tasks = [
  { id: 1, task_name: 'Update APIS retention logic to 5 years', owner_team: 'Data Governance', priority: 'HIGH', due_days: 14, status: 'OPEN', detail: 'Change the purge job in APIS Scheduler from 3 to 5 years.', evidence: 'Clause 4.2; Policy PDP-2.0 s.5.3' },
  { id: 2, task_name: 'Modify Passenger Data Policy s.5.3', owner_team: 'Data Governance', priority: 'HIGH', due_days: 10, status: 'IN_PROGRESS', detail: 'Apply the approved draft D-07.', evidence: 'Draft D-07' },
  { id: 3, task_name: 'Validate archive process', owner_team: 'IT Operations', priority: 'MEDIUM', due_days: 21, status: 'REVIEW', detail: 'Confirm archived records remain retrievable for 5 years.', evidence: 'Test plan TP-12' },
  { id: 4, task_name: 'Publish SOP-API-01 v1.4', owner_team: 'Flight Operations', priority: 'LOW', due_days: 0, status: 'DONE', detail: 'Published after approval.', evidence: 'Audit event 09:21' },
  { id: 5, task_name: 'Create CTRL-004 encryption at rest', owner_team: 'Information Security', priority: 'MEDIUM', due_days: 30, status: 'OPEN', detail: 'Define AES-256 control for passport data.', evidence: 'Gap 6.1' },
  { id: 6, task_name: 'Add 24-hour regulator notification to incident SOP', owner_team: 'Flight Operations', priority: 'HIGH', due_days: 12, status: 'IN_PROGRESS', detail: 'Update the escalation steps and owners.', evidence: 'Clause 4.5; Draft D-08' },
];

// Approval queue (Compliance Review & Approval Center)
export const approvals = [
  { id: 'A-1', title: 'DGCA CAR Sec 5 Series X', change: 'Retention increase: 3 to 5 years (Clause 4.2)', severity: 'HIGH', confidence: 95, affected_assets: 4, status: 'PROPOSED' },
  { id: 'A-2', title: 'DPDP Passport Data Notification', change: 'Encryption at rest for passport data (Clause 6.1)', severity: 'HIGH', confidence: 92, affected_assets: 3, status: 'PROPOSED' },
  { id: 'A-3', title: 'BCAS Security Directive 2026-07', change: 'Quarterly access reviews (Clause 6.3)', severity: 'MEDIUM', confidence: 88, affected_assets: 2, status: 'PROPOSED' },
  { id: 'A-4', title: 'ICAO Annex 17 Amendment', change: 'Visitor pass retention wording', severity: 'MEDIUM', confidence: 84, affected_assets: 2, status: 'PROPOSED' },
];

// Knowledge hub
export const policies = [
  { code: 'PDP-2.0', name: 'Passenger Data Policy', version: 'V2.0', owner: 'Data Governance', status: 'Active' },
  { code: 'CYB-1.4', name: 'Cyber Security Policy', version: 'V1.4', owner: 'Information Security', status: 'Active' },
  { code: 'AAP-3.0', name: 'Airport Access Policy', version: 'V3.0', owner: 'Airport Operations', status: 'Active' },
];
export const sops = [
  { code: 'SOP-GH-01', name: 'Ground Handling', version: 'V2.2', owner: 'Ground Operations', status: 'Active' },
  { code: 'SOP-API-01', name: 'API Processing', version: 'V1.4', owner: 'Flight Operations', status: 'Active' },
  { code: 'SOP-CR-01', name: 'Crew Operations', version: 'V4.0', owner: 'Crew Management', status: 'Active' },
];
export const controls = [
  { code: 'CTRL-001', name: 'APIS Data Retention', owner: 'Data Governance', status: 'Active' },
  { code: 'CTRL-002', name: 'Encryption Control', owner: 'Information Security', status: 'Active' },
  { code: 'CTRL-003', name: 'Access Reviews', owner: 'Information Security', status: 'Active' },
];
export const versionHistory = [
  { version: 'V1.0', status: 'Active', note: 'Initial publication' },
  { version: 'V2.0', status: 'Draft', note: 'Retention review in progress' },
  { version: 'V2.1', status: 'Approved', note: 'Effective from 01-Jan-2027' },
];

// Audit trail events
export const auditEvents = [
  { id: 1, time: '09:10', type: 'Regulation', event: 'DGCA circular detected', actor: 'Monitoring Agent', doc: 'DGCA-CAR-SEC5-X', detail: 'Downloaded, hashed and registered as a new document.' },
  { id: 2, time: '09:12', type: 'Regulation', event: 'Obligations extracted', actor: 'Extraction Agent', doc: 'DGCA-CAR-SEC5-X', detail: '5 obligations extracted, 0 dropped for low confidence.' },
  { id: 3, time: '09:14', type: 'Gap', event: 'Gap identified', actor: 'Gap Agent', doc: 'DGCA-CAR-SEC5-X', detail: 'Retention mismatch (3 years vs 5 years), severity HIGH.' },
  { id: 4, time: '09:15', type: 'Policy', event: 'Draft generated', actor: 'Draft Agent', doc: 'PDP-2.0', detail: 'Draft D-07 created for Passenger Data Policy s.5.3.' },
  { id: 5, time: '09:20', type: 'Approval', event: 'Approved', actor: 'Compliance Officer (demo)', doc: 'PDP-2.0', detail: 'Approved with comment: align CTRL-001 with the same change.' },
  { id: 6, time: '09:21', type: 'Knowledge', event: 'Version 2 published', actor: 'Knowledge Base Agent', doc: 'PDP-2.0', detail: 'V2.1 published, effective 01-Jan-2027.' },
];

// Repository health and self-healing demo
export const repoHealth = {
  available: 143,
  missing: 1,
  missingFile: 'DGCA_CAR_API_Retention.pdf',
  steps: ['Detected missing file', 'Verified source', 'Downloaded latest version', 'Re-indexed', 'Completed'],
};

export const agents = [
  { name: 'Monitoring Agent', status: 'Healthy' },
  { name: 'Extraction Agent', status: 'Healthy' },
  { name: 'Mapping Agent', status: 'Running' },
  { name: 'Gap Agent', status: 'Healthy' },
  { name: 'Draft Agent', status: 'Healthy' },
  { name: 'Repository Agent', status: 'Self-Healing' },
];

export const sources = [
  { name: 'DGCA', type: 'Regulator', status: 'Healthy', lastChecked: '5 mins ago' },
  { name: 'BCAS', type: 'Regulator', status: 'Healthy', lastChecked: '5 mins ago' },
  { name: 'ICAO', type: 'Regulator', status: 'Healthy', lastChecked: '12 mins ago' },
  { name: 'IATA', type: 'Industry body', status: 'Healthy', lastChecked: '1 hour ago' },
  { name: 'CERT-IN', type: 'Regulator', status: 'Healthy', lastChecked: '5 mins ago' },
  { name: 'DPDP', type: 'Regulator', status: 'Healthy', lastChecked: '20 mins ago' },
];

export const users = [
  { name: 'Compliance Officer (demo)', role: 'Approver' },
  { name: 'Legal Lead (demo)', role: 'Reviewer' },
  { name: 'InfoSec Analyst (demo)', role: 'Editor' },
  { name: 'Data Governance Lead (demo)', role: 'Policy owner' },
  { name: 'Internal Auditor (demo)', role: 'Read only' },
  { name: 'Executive (demo)', role: 'Viewer' },
];

export const demoWorkflow = [
  'New DGCA circular',
  '5 obligations',
  '3 impacted policies',
  '2 compliance gaps',
  'Policy draft',
  'Approval',
  'Published',
];

// Copilot (grounded answers with citations, dummy)
export const copilotSuggestions = [
  'Which policies are impacted by the latest DGCA retention requirements?',
  'Show all open high-risk compliance gaps.',
  'Can passport copies be stored in SharePoint?',
];

export function askCopilot(question) {
  const q = question.toLowerCase();
  if (q.includes('retention') || q.includes('impacted')) {
    return {
      text: 'The DGCA retention requirement (Clause 4.2) impacts the Passenger Data Policy s.5.3, control CTRL-001 and the APIS Scheduler. The current provision is 3 years against a 5-year requirement.',
      sources: ['DGCA CAR Sec 5 Series X', 'Passenger Data Policy v2.0'],
    };
  }
  if (q.includes('gap')) {
    return {
      text: 'There are 3 high-risk open gaps: retention mismatch (4.2), missing 24-hour regulator notification (4.5) and missing AES-256 control (6.1).',
      sources: ['Gap analysis: DGCA CAR Sec 5 Series X', 'Cyber Security Policy v1.4'],
    };
  }
  if (q.includes('passport') || q.includes('sharepoint')) {
    return {
      text: 'Passport copies may be stored in SharePoint only through approved channels, with encryption at rest (Clause 6.1) and access limited to reviewed roles.',
      sources: ['DPDP Passport Data Notification', 'DGCA guidelines', 'Cyber Security Policy v1.4'],
    };
  }
  return {
    text: 'No grounded answer was found in approved policies or regulator documents for this question. Try rephrasing it or check the Regulations repository.',
    sources: [],
  };
}
