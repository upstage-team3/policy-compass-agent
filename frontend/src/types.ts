export interface PolicyCard {
  id: string;
  name: string;
  target: string;
  amount: string;
  period: string;
  reason: string;
  url?: string;
  ministry: string;
  category: string;
  region: string;
  scope: "exact" | "nationwide" | "nearby_reference" | "excluded";
  distanceKm?: number | null;
  matchScore?: number;
  evidenceCoverage?: number;
}

export type MessageRole = "user" | "assistant";

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: Date;
  policyCards?: PolicyCard[];
}

export interface Chat {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
}
