export type AgentName = "boss" | "inventory" | "accounting" | "facilities" | "customer_service";

export interface Fact {
  source_tool: string;
  detail: string;
}

export interface SpecialistReport {
  agent: AgentName;
  ticket_id: number;
  summary: string;
  facts: Fact[];
  approval_requests_created: number[];
  recommendation: string;
  needs_human_approval: boolean;
  blocked: string | null;
}

export interface ApprovalItem {
  request_id: number;
  kind: ApprovalKind;
  amount: number;
  description: string;
}

export interface TicketResolution {
  ticket_id: number;
  final_status: string;
  summary: string;
  agents_consulted: AgentName[];
  decisions: string[];
  approvals_needed: ApprovalItem[];
  customer_message: string | null;
  risks: string[];
}

export interface RunState {
  ticket_id: number;
  session_id: string;
  status: "running" | "done" | "failed";
  started_at: string;
  finished_at: string | null;
  error: string | null;
  result: TicketResolution | null;
}

export interface Ticket {
  id: number;
  title: string;
  type: string;
  requester: string;
  status: "open" | "resolved";
  detailed_status: string;
  last_run: RunState | null;
}

export interface AgentEvent {
  id: number;
  timestamp: string;
  ticket_id: number;
  session_id: string;
  agent: AgentName;
  delegated_by: AgentName | null;
  depth: number;
  step: number;
  kind: "step" | "final" | "error";
  message: string;
  tools_used: string[];
  tool_calls: { tool: string; args: Record<string, unknown> }[];
  delegated_to: AgentName[];
  tokens: number;
  result: SpecialistReport | TicketResolution | null;
}

export type ApprovalKind = "rent" | "invoice" | "purchase_order" | "price_override";

export interface Approval {
  id: number;
  ticket_id: number;
  kind: ApprovalKind;
  ref_id: number | null;
  vendor_id: number | null;
  sku: string | null;
  size: string | null;
  qty: number | null;
  amount: number;
  account: string | null;
  details: string;
  requested_by: AgentName;
  status: string;
  created_at: string;
  moves_cash: boolean;
}

export interface Cash {
  account: string;
  balance: number;
  as_of: string;
  pending_outflow: number;
  balance_if_all_pending_approved: number;
}

export interface ApproveResult {
  cash_moved: boolean;
  balance_before?: number;
  balance_after?: number;
  approval_request: Approval;
}
