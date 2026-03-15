import { useState, useRef, useEffect } from "react";
import {
  BrainCircuit,
  X,
  Send,
  Trash2,
  Sparkles,
} from "lucide-react";
import { useChat, type ChatMessage } from "../context/ChatContext";
import { cn } from "../lib/utils";
import { AssistantMarkdown } from "./chat/AssistantMarkdown";

const SUGGESTED_PROMPTS = [
  "Analyze the current threat landscape",
  "Explain the prompt injection attack",
  "Generate a remediation plan",
  "What RBAC policies are at risk?",
];

function MessageBubble({ message, isStreaming }: { message: ChatMessage; isStreaming?: boolean }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-xl px-3 py-2 text-xs leading-relaxed",
          isUser
            ? "bg-primary/10 text-text border border-primary/20"
            : "bg-surface-alt text-text border border-border",
        )}
      >
        {isUser ? (
          message.content
        ) : message.content ? (
          <AssistantMarkdown markdown={message.content} isStreaming={isStreaming} />
        ) : (
          <TypingIndicator />
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 py-1 px-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-text-muted animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </div>
  );
}

export function AIChatPanel() {
  const {
    messages,
    isStreaming,
    nodeContext,
    isOpen,
    setIsOpen,
    setNodeContext,
    sendMessage,
    clearHistory,
  } = useChat();
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    sendMessage(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      {/* Floating toggle button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-5 right-5 z-50 p-3.5 rounded-full bg-primary text-white shadow-lg hover:bg-primary-hover transition-all hover:scale-105 active:scale-95"
          aria-label="Open AI Chat"
        >
          <BrainCircuit className="w-5 h-5" />
          {/* Pulse ring */}
          <span className="absolute inset-0 rounded-full bg-primary/30 animate-ping" />
        </button>
      )}

      {/* Chat panel */}
      <div
        className={cn(
          "fixed bottom-5 right-5 z-50 w-96 h-[520px] flex flex-col bg-surface-raised border border-border rounded-2xl shadow-2xl overflow-hidden",
          "transition-all duration-300",
          isOpen
            ? "opacity-100 translate-y-0 scale-100"
            : "opacity-0 translate-y-4 scale-95 pointer-events-none",
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-surface-alt flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-primary/10">
              <BrainCircuit className="w-4 h-4 text-primary" />
            </div>
            <div>
              <h3 className="text-xs font-semibold text-text">Manifold AI</h3>
              <p className="text-[9px] text-text-muted">Security Analysis Assistant</p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={clearHistory}
              className="p-1.5 rounded-lg hover:bg-surface transition-colors text-text-muted hover:text-text"
              title="Clear history"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1.5 rounded-lg hover:bg-surface transition-colors text-text-muted hover:text-text"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Context badge */}
        {nodeContext && (
          <div className="flex items-center gap-2 px-4 py-2 bg-primary/5 border-b border-border">
            <span className="text-[10px] text-text-muted">Context:</span>
            <span className="text-[10px] font-mono font-semibold text-primary">
              {nodeContext.nodeName}
            </span>
            <span
              className={cn(
                "text-[9px] px-1.5 py-0.5 rounded-full font-semibold",
                nodeContext.status === "compromised"
                  ? "bg-compromised/10 text-compromised"
                  : nodeContext.status === "warning"
                    ? "bg-suspicious/10 text-suspicious"
                    : "bg-healthy/10 text-healthy",
              )}
            >
              {nodeContext.status}
            </span>
            <button
              onClick={() => setNodeContext(null)}
              className="ml-auto p-0.5 rounded hover:bg-surface-alt text-text-muted"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        )}

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <div className="p-3 rounded-2xl bg-primary/10 mb-3">
                <Sparkles className="w-6 h-6 text-primary" />
              </div>
              <p className="text-sm font-semibold text-text mb-1">
                Manifold Security AI
              </p>
              <p className="text-xs text-text-muted mb-4 max-w-[240px]">
                Ask me about threats, vulnerabilities, or get remediation guidance for your system.
              </p>
              <div className="flex flex-col gap-1.5 w-full">
                {SUGGESTED_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => sendMessage(prompt)}
                    className="text-left text-[11px] px-3 py-2 rounded-lg border border-border bg-surface hover:bg-surface-alt hover:border-primary/30 text-text-muted hover:text-text transition-all"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <MessageBubble
                key={msg.id}
                message={msg}
                isStreaming={isStreaming && msg.role === "assistant" && idx === messages.length - 1}
              />
            ))
          )}
        </div>

        {/* Input */}
        <div className="px-3 py-3 border-t border-border flex-shrink-0">
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about security threats…"
              rows={1}
              className="flex-1 resize-none px-3 py-2 text-xs bg-surface-alt border border-border rounded-lg text-text placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary max-h-20"
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || isStreaming}
              className={cn(
                "p-2 rounded-lg transition-all flex-shrink-0",
                input.trim() && !isStreaming
                  ? "bg-primary text-white hover:bg-primary-hover"
                  : "bg-surface-alt text-text-muted cursor-not-allowed",
              )}
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
