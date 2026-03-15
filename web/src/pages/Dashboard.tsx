import { useState, useEffect, useRef, useCallback } from "react";
import { useAuth } from "../auth";
import { apiFetch } from "../auth/api";
import { getOrMintToken } from "../auth/token";
import { API_BASE } from "../lib/apiBase";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardDescription,
} from "../components/Card";
import { Button } from "../components/Button";

// Types for backend responses
interface UploadItem {
  id: string;
  original_filename: string;
  content_type: string;
  byte_size: number;
  extraction_job_id: string | null;
  created_at: string;
}

interface JobItem {
  id: string;
  kind: string;
  status: string;
  progress: number;
  error: string | null;
  created_at: string;
}

export function Dashboard() {
  const { user, userId, deviceId, role, displayName } = useAuth();
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiResponse, setAiResponse] = useState("");
  const [aiStreaming, setAiStreaming] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadUploads = useCallback(async () => {
    try {
      const res = await apiFetch<UploadItem[]>("/uploads");
      if (res.ok) setUploads(res.data);
    } catch (err) {
      console.warn("Failed to load uploads", err);
    }
  }, []);

  const loadJobs = useCallback(async () => {
    try {
      const res = await apiFetch<JobItem[]>("/jobs");
      if (res.ok) setJobs(res.data);
    } catch (err) {
      console.warn("Failed to load jobs", err);
    }
  }, []);

  useEffect(() => {
    loadUploads();
    loadJobs();
  }, [loadUploads, loadJobs]);

  const handleUpload = async () => {
    const file = fileInputRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const token = await getOrMintToken("http");
      const res = await fetch(`${API_BASE}/uploads`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (res.ok) {
        if (fileInputRef.current) fileInputRef.current.value = "";
        await loadUploads();
        await loadJobs();
      }
    } finally {
      setUploading(false);
    }
  };

  const handleAiStream = async () => {
    if (!aiPrompt.trim()) return;
    setAiStreaming(true);
    setAiResponse("");
    try {
      const token = await getOrMintToken("http");
      const res = await fetch(`${API_BASE}/llm/chat/stream`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message: aiPrompt, context: {} }),
      });
      if (!res.ok || !res.body) {
        setAiResponse("Error: Could not connect to LLM service");
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("data:")) {
            try {
              const data = JSON.parse(line.slice(5).trim());
              if (data.token) {
                setAiResponse((prev) => prev + data.token);
              } else if (data.error) {
                setAiResponse((prev) => prev + `\n[Error: ${data.error}]`);
              }
            } catch {
              /* skip malformed */
            }
          }
        }
      }
    } catch {
      setAiResponse("Error: Stream failed");
    } finally {
      setAiStreaming(false);
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div>
        <h1
          className="text-3xl font-bold tracking-tight"
          data-testid="dashboard-heading"
        >
          Dashboard
        </h1>
        <p className="text-text-muted mt-1">
          Welcome back,{" "}
          <span className="font-semibold text-text">
            {displayName || userId}
          </span>
        </p>
      </div>

      {/* Session Info */}
      <Card>
        <CardHeader>
          <CardTitle>Session</CardTitle>
          <CardDescription>Current authenticated session details</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-text-muted">User ID</span>
              <p className="font-mono text-xs truncate">{userId}</p>
            </div>
            <div>
              <span className="text-text-muted">Device ID</span>
              <p className="font-mono text-xs truncate">{deviceId}</p>
            </div>
            <div>
              <span className="text-text-muted">Role</span>
              <p className="font-semibold">{role}</p>
            </div>
            <div>
              <span className="text-text-muted">Display Name</span>
              <p>{displayName || "—"}</p>
            </div>
            <div>
              <span className="text-text-muted">Scopes</span>
              <p className="font-mono text-xs">
                {user?.scopes?.join(", ") || "none"}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {/* File Upload */}
        <Card>
          <CardHeader>
            <CardTitle>File Upload</CardTitle>
            <CardDescription>Upload files to your storage</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="flex gap-2">
                <input
                  ref={fileInputRef}
                  type="file"
                  className="flex-1 text-sm file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:text-sm file:bg-primary file:text-white"
                />
                <Button onClick={handleUpload} disabled={uploading}>
                  {uploading ? "Uploading…" : "Upload"}
                </Button>
              </div>
              {uploads.length > 0 && (
                <div className="space-y-2">
                  <p className="text-sm font-medium">Recent Uploads</p>
                  {uploads.slice(0, 5).map((u) => (
                    <div
                      key={u.id}
                      className="flex items-center justify-between text-sm p-2 bg-surface-alt rounded"
                    >
                      <div className="truncate flex-1">
                        <span className="font-medium">
                          {u.original_filename}
                        </span>
                        <span className="text-text-muted ml-2">
                          ({(u.byte_size / 1024).toFixed(1)} KB)
                        </span>
                      </div>
                      <span className="text-xs text-text-muted ml-2">
                        {u.extraction_job_id ? "📝 Extracted" : ""}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Recent Jobs */}
        <Card>
          <CardHeader>
            <CardTitle>Background Jobs</CardTitle>
            <CardDescription>Recent job activity</CardDescription>
          </CardHeader>
          <CardContent>
            {jobs.length === 0 ? (
              <p className="text-sm text-text-muted">
                No jobs yet. Upload a text file to create one.
              </p>
            ) : (
              <div className="space-y-2">
                {jobs.slice(0, 5).map((j) => (
                  <div
                    key={j.id}
                    className="flex items-center justify-between text-sm p-2 bg-surface-alt rounded"
                  >
                    <div>
                      <span className="font-medium">{j.kind}</span>
                      <span
                        className={`ml-2 text-xs px-1.5 py-0.5 rounded ${
                          j.status === "succeeded"
                            ? "bg-green-100 text-green-700"
                            : j.status === "failed"
                              ? "bg-red-100 text-red-700"
                              : j.status === "running"
                                ? "bg-blue-100 text-blue-700"
                                : "bg-gray-100 text-gray-700"
                        }`}
                      >
                        {j.status}
                      </span>
                    </div>
                    {j.progress > 0 && j.progress < 100 && (
                      <span className="text-xs">{j.progress}%</span>
                    )}
                  </div>
                ))}
              </div>
            )}
            <Button className="mt-4 w-full" onClick={loadJobs}>
              Refresh
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* AI Stream */}
      <Card>
        <CardHeader>
          <CardTitle>AI Chat</CardTitle>
          <CardDescription>
            Stream responses from the LLM endpoint
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <textarea
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              placeholder="Type a prompt…"
              className="w-full h-24 p-3 rounded border border-border bg-surface text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <Button
              onClick={handleAiStream}
              disabled={aiStreaming || !aiPrompt.trim()}
            >
              {aiStreaming ? "Streaming…" : "Send"}
            </Button>
            {aiResponse && (
              <div className="p-3 rounded bg-surface-alt text-sm whitespace-pre-wrap font-mono">
                {aiResponse}
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
