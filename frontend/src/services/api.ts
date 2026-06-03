import type {
  VehicleQueryRequest, VehicleCompareRequest, RecommendRequest,
  ApiResponse, CompareResult, RecommendResult,
  HealthResponse,
  // Legacy
  AgentState, ConfigSettings, UpdateConfigPayload,
  PdfUploadResponse, DatasetSummary, EvalRunRequest,
  EvalRunResponse, WeightSweepRequest,
} from '../types';

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

// =========================================================================
// V2 API — 高并发接口
// =========================================================================

/** 车型查询 */
export async function vehicleQuery(data: VehicleQueryRequest): Promise<ApiResponse<{ answer: string }>> {
  return request<ApiResponse<{ answer: string }>>('/v1/vehicle/query', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/** 多车对比 */
export async function vehicleCompare(data: VehicleCompareRequest): Promise<ApiResponse<CompareResult>> {
  return request<ApiResponse<CompareResult>>('/v1/vehicle/compare', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/** 智能推荐 */
export async function recommend(data: RecommendRequest): Promise<ApiResponse<RecommendResult>> {
  return request<ApiResponse<RecommendResult>>('/v1/recommend', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

/** 关闭会话 */
export async function closeSession(sessionId: string, userId: string): Promise<ApiResponse> {
  return request<ApiResponse>('/v1/session/close', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, user_id: userId }),
  });
}

/** 健康检查 (v2) */
export async function healthCheckV2(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

// =========================================================================
// Legacy API — 设置 / 评测 / 索引 (保持不变)
// =========================================================================

export async function getAgentState(): Promise<AgentState> {
  return request<AgentState>('/state');
}

export async function clearSession(): Promise<{ status: string }> {
  return request('/clear', { method: 'POST' });
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

export async function runSweep(data: WeightSweepRequest): Promise<EvalRunResponse[]> {
  return request<EvalRunResponse[]>('/eval/sweep', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}
