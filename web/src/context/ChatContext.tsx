import {
  createContext,
  useContext,
  useState,
  useCallback,
  useRef,
  type ReactNode,
} from "react";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { API_BASE } from "../lib/apiBase";

export interface NodeContext {
  nodeId: string;
  nodeName: string;
  status: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}

interface ChatContextValue {
  messages: ChatMessage[];
  isStreaming: boolean;
  nodeContext: NodeContext | null;
  isOpen: boolean;
  setNodeContext: (ctx: NodeContext | null) => void;
  setIsOpen: (open: boolean) => void;
  sendMessage: (text: string) => void;
  clearHistory: () => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

let msgId = 0;

// Dev/demo fallback: only enabled when VITE_ENABLE_MOCK_CHAT is explicitly "true"
const MOCK_ENABLED = import.meta.env.VITE_ENABLE_MOCK_CHAT === "true";

// Mock responses keyed by context — only used when MOCK_ENABLED
const MOCK_RESPONSES: Record<string, string> = {
  default:
    "**Security Analysis Complete**\n\nBased on the current system topology, I've identified the following:\n\n1. **Active Threat**: The Context Agent (LLM-AGENT) shows signs of prompt injection compromise. Egress traffic is 3.8x above baseline.\n\n2. **Lateral Movement Risk**: The compromised agent has active MCP bridge access to the Core API Hub, creating a potential exfiltration channel.\n\n3. **Recommended Actions**:\n   - Isolate the Context Agent immediately\n   - Revoke `vector_read_role` and `mcp_bridge_role`\n   - Audit all tool call logs from the last 6 hours\n   - Deploy input sanitization middleware before restoring service",
  compromised:
    "**CRITICAL: Node Compromise Detected**\n\nThis entity is actively compromised. Analysis shows:\n\n- **Attack Vector**: Prompt injection via malicious PDF documents uploaded through the ingestion endpoint\n- **Impact**: The agent is executing attacker-controlled instructions, bypassing content policy filters via role-play jailbreak\n- **Exfiltration**: Anomalous tool call volume at 412 calls/min (baseline: 18). Outbound data transfer 3.8x above normal\n\n**Immediate Remediation Steps**:\n1. Isolate this entity to block all network traffic\n2. Revoke all RBAC role bindings\n3. Preserve tool call logs for forensic analysis\n4. Redeploy with input sanitization middleware",
  warning:
    "**WARNING: Anomalous Behavior Detected**\n\nThis node shows concerning patterns that warrant investigation:\n\n- Traffic patterns deviate from 7-day baseline by 2x\n- Potential downstream impact from compromised upstream services\n- RBAC policies may need tightening\n\n**Recommendations**:\n1. Monitor egress traffic closely\n2. Review and rotate credentials\n3. Enable query-level audit logging",
  healthy:
    "**Node Status: Healthy**\n\nThis entity is operating within normal parameters.\n\n- All telemetry metrics within expected ranges\n- No anomalous traffic patterns detected\n- RBAC policies are correctly scoped\n\nNo immediate action required. Consider scheduling routine credential rotation.",
};

// Stable thread ID per browser session for conversation continuity
let _threadId: string | null = null;
function getThreadId(): string {
  if (!_threadId) {
    _threadId = `thread-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }
  return _threadId;
}

export function ChatProvider({ children }: { children: ReactNode }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [nodeContext, setNodeContext] = useState<NodeContext | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    (text: string) => {
      const userMsg: ChatMessage = {
        id: `msg-${++msgId}`,
        role: "user",
        content: text,
      };
      const assistantId = `msg-${++msgId}`;
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsStreaming(true);

      // Abort any prior stream
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      // Build recent history for the backend (last 10 messages)
      const recentHistory = [...messages, userMsg]
        .slice(-10)
        .map((m) => ({ role: m.role, content: m.content }));

      // Try real endpoint; only fall back to mock in dev/demo mode
      const streamReal = async () => {
        try {
          await fetchEventSource(`${API_BASE}/llm/chat/stream`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              message: text,
              context: nodeContext
                ? {
                    nodeId: nodeContext.nodeId,
                    nodeName: nodeContext.nodeName,
                    status: nodeContext.status,
                  }
                : undefined,
              thread_id: getThreadId(),
              history: recentHistory,
            }),
            signal: ctrl.signal,
            openWhenHidden: true,
            onmessage(ev) {
              try {
                const data = JSON.parse(ev.data) as { token?: string };
                if (data.token) {
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantId
                        ? { ...m, content: m.content + data.token }
                        : m,
                    ),
                  );
                }
              } catch {
                // ignore parse errors
              }
            },
            onclose() {
              setIsStreaming(false);
            },
            onerror() {
              if (MOCK_ENABLED) {
                simulateMock(assistantId);
              } else {
                // Production: surface the error
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? {
                          ...m,
                          content:
                            m.content +
                            "\n\n**Error:** Unable to reach the AI backend. Please try again later.",
                        }
                      : m,
                  ),
                );
                setIsStreaming(false);
              }
              throw new Error("stop"); // stop retry
            },
          });
        } catch {
          // If fetch itself fails
          if (!ctrl.signal.aborted) {
            if (MOCK_ENABLED) {
              simulateMock(assistantId);
            } else {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? {
                        ...m,
                        content:
                          m.content +
                          "\n\n**Error:** Unable to reach the AI backend. Please try again later.",
                      }
                    : m,
                ),
              );
              setIsStreaming(false);
            }
          }
        }
      };

      const simulateMock = (asstId: string) => {
        const mockKey = nodeContext?.status ?? "default";
        const response =
          MOCK_RESPONSES[mockKey] ?? MOCK_RESPONSES.default ?? "";
        const tokens = response.split("");
        let i = 0;
        const interval = setInterval(() => {
          if (i >= tokens.length || ctrl.signal.aborted) {
            clearInterval(interval);
            setIsStreaming(false);
            return;
          }
          // Deliver in chunks of 3 chars for speed
          const chunk = tokens.slice(i, i + 3).join("");
          setMessages((prev) =>
            prev.map((m) =>
              m.id === asstId ? { ...m, content: m.content + chunk } : m,
            ),
          );
          i += 3;
        }, 20);
      };

      void streamReal();
    },
    [nodeContext, messages],
  );

  const clearHistory = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setIsStreaming(false);
    // Reset thread ID so next conversation starts fresh
    _threadId = null;
  }, []);

  return (
    <ChatContext.Provider
      value={{
        messages,
        isStreaming,
        nodeContext,
        isOpen,
        setNodeContext,
        setIsOpen,
        sendMessage,
        clearHistory,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used within ChatProvider");
  return ctx;
}
