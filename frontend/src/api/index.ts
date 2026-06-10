import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
})

export interface Layer {
  id: string
  name: string
  salt: string
  description: string | null
  created_at: string
  updated_at: string
}

export interface Group {
  id: string
  name: string
  traffic_percentage: number
  config_json: Record<string, unknown> | null
  created_at: string
}

export interface RolloutStep {
  traffic_percentage: number
  hold_seconds: number
}

export interface GuardrailMetric {
  metric_name: string
  threshold: number
  direction: 'up' | 'down'
}

export interface Experiment {
  id: string
  layer_id: string
  key: string
  name: string
  description: string | null
  status: string
  bucket_start: number
  bucket_end: number
  winner_group_id: string | null
  rollout_steps: RolloutStep[] | null
  current_step_index: number | null
  guardrail_metrics: GuardrailMetric[] | null
  created_by: string | null
  created_at: string
  updated_at: string
  groups: Group[]
}

export interface RolloutStepLog {
  id: string
  step_index: number
  traffic_percentage: number
  trigger_type: string
  triggered_by: string | null
  created_at: string
}

export interface RolloutStatus {
  current_step_index: number | null
  current_traffic_percentage: number | null
  steps: RolloutStep[]
  step_logs: RolloutStepLog[]
}

export interface GroupStats {
  group_name: string
  total_users: number
  conversions: number
  conversion_rate: number
  ci_lower: number
  ci_upper: number
}

export interface ExperimentStats {
  experiment_id: string
  goal_event: string
  groups: GroupStats[]
  z_statistic: number | null
  p_value: number | null
  is_significant: boolean
  recommended_sample_size: number | null
}

export const layerApi = {
  list: () => api.get<Layer[]>('/layers').then(r => r.data),
  create: (data: { name: string; description?: string }) =>
    api.post<Layer>('/layers', data).then(r => r.data),
}

export const experimentApi = {
  list: (params?: { status?: string; layer_id?: string }) =>
    api.get<{ items: Experiment[]; total: number }>('/experiments', { params }).then(r => r.data),
  get: (id: string) => api.get<Experiment>(`/experiments/${id}`).then(r => r.data),
  create: (data: {
    layer_id: string
    key: string
    name: string
    description?: string
    bucket_start: number
    bucket_end: number
    groups: { name: string; traffic_percentage: number; config_json?: Record<string, unknown> }[]
    rollout_steps?: RolloutStep[]
    guardrail_metrics?: GuardrailMetric[]
  }) => api.post<Experiment>('/experiments', data).then(r => r.data),
  update: (id: string, data: { name?: string; description?: string }) =>
    api.put<Experiment>(`/experiments/${id}`, data).then(r => r.data),
  start: (id: string) => api.post<Experiment>(`/experiments/${id}/start`).then(r => r.data),
  pause: (id: string) => api.post<Experiment>(`/experiments/${id}/pause`).then(r => r.data),
  resume: (id: string) => api.post<Experiment>(`/experiments/${id}/resume`).then(r => r.data),
  rollout: (id: string, winnerGroupId: string) =>
    api.post<Experiment>(`/experiments/${id}/rollout?winner_group_id=${winnerGroupId}`).then(r => r.data),
  stats: (id: string, goalEvent: string) =>
    api.get<ExperimentStats>(`/experiments/${id}/stats`, { params: { goal_event: goalEvent } }).then(r => r.data),
  advanceRollout: (id: string, confirmed = false) =>
    api.post<Experiment>(`/experiments/${id}/rollout-advance`, { confirmed }).then(r => r.data),
  rollbackRollout: (id: string) =>
    api.post<Experiment>(`/experiments/${id}/rollout-rollback`).then(r => r.data),
  rolloutStatus: (id: string) =>
    api.get<RolloutStatus>(`/experiments/${id}/rollout-status`).then(r => r.data),
}

export default api
