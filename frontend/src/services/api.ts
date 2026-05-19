import type { ChatRequest, ChatResponse, AgentState, ConfigSettings, UpdateConfigPayload, PdfUploadResponse, DatasetSummary, EvalRunRequest, EvalRunResponse } from '../types';

const BASE = '/api';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const errorText = await res.text().catch(() => 'Unknown error');
    throw new Error(`API error ${res.status}: ${errorText}`);
  }
  return res.json();
}

export async function sendChat(data: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>('/chat', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function indexKnowledge(filePath: string): Promise<{ status: string; chunks: number }> {
  return request('/index', {
    method: 'POST',
    body: JSON.stringify({ file_path: filePath }),
  });
}

export async function clearSession(): Promise<{ status: string }> {
  return request('/clear', { method: 'POST' });
}

export async function getAgentState(): Promise<AgentState> {
  return request<AgentState>('/state');
}

export async function healthCheck(): Promise<{ status: string }> {
  return request('/health');
}

export async function getConfig(): Promise<ConfigSettings> {
  return request<ConfigSettings>('/config');
}

export async function updateConfig(data: UpdateConfigPayload): Promise<{ status: string; updated: string[] }> {
  return request('/config', {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function uploadPdf(file: File): Promise<PdfUploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch('/api/upload-pdf', {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    throw new Error(`Upload failed: ${res.status}`);
  }
  return res.json();
}

export async function getDatasets(): Promise<DatasetSummary[]> {
  return request<DatasetSummary[]>('/eval/datasets');
}

export async function runEval(data: EvalRunRequest): Promise<EvalRunResponse> {
  return request<EvalRunResponse>('/eval/run', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}
