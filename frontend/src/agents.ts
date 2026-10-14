import { Building2, Calculator, Crown, Headset, Package, type LucideIcon } from "lucide-react";
import type { AgentName } from "./types";

export interface AgentMeta {
  name: AgentName;
  label: string;
  role: string;
  color: string; // used via the --agent CSS variable
  icon: LucideIcon;
}

export const AGENTS: AgentMeta[] = [
  { name: "boss", label: "Boss", role: "Routes tickets, owns the call", color: "#f5b83d", icon: Crown },
  { name: "inventory", label: "Inventory", role: "Stock, vendors, restock", color: "#2dd4bf", icon: Package },
  { name: "accounting", label: "Accounting", role: "Invoices, cash, margins", color: "#a78bfa", icon: Calculator },
  { name: "facilities", label: "Facilities", role: "Lease and rent notices", color: "#fb8c5a", icon: Building2 },
  { name: "customer_service", label: "Customer Service", role: "What the customer hears", color: "#60a5fa", icon: Headset },
];

export const AGENT_BY_NAME = Object.fromEntries(AGENTS.map((a) => [a.name, a])) as Record<
  AgentName,
  AgentMeta
>;
