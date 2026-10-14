import type { AgentEvent, Approval, ApproveResult, Cash, RunState, Ticket } from "./types";

export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    const message = Array.isArray(detail)
      ? detail.map((d: { msg: string }) => d.msg).join("; ")
      : (detail ?? res.statusText);
    throw new ApiError(res.status, message);
  }
  return body as T;
}

export const api = {
  tickets: () => request<Ticket[]>("/tickets"),
  run: (ticketId: number) =>
    request<Pick<RunState, "ticket_id" | "session_id" | "status">>(`/tickets/${ticketId}/run`, {
      method: "POST",
    }),
  events: (ticketId: number, since?: number) => {
    const params = new URLSearchParams({ ticket_id: String(ticketId) });
    if (since !== undefined) params.set("since", String(since));
    return request<{ events: AgentEvent[]; last_id: number | null }>(`/events?${params}`);
  },
  approvals: () => request<Approval[]>("/approvals"),
  approve: (id: number, approvedBy: string) =>
    request<ApproveResult>(`/approvals/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ approved_by: approvedBy }),
    }),
  cash: () => request<Cash>("/cash"),
  reset: () => request<{ reset: boolean }>("/reset", { method: "POST" }),
};
