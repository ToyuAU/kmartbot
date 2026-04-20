/**
 * Typed REST API client.
 * All methods throw on non-2xx responses.
 */

export interface Profile {
  id: string
  name: string
  first_name: string
  last_name: string
  email: string
  mobile: string
  address1: string
  address2: string
  city: string
  state: string
  postcode: string
  country: string
  flybuys: string
  created_at: string
}

export interface Card {
  id: string
  alias: string
  cardholder: string
  number: string
  expiry_month: string
  expiry_year: string
  cvv: string
  created_at: string
}

export interface Task {
  id: string
  name: string
  site: string
  sku: string
  profile_id: string
  card_ids: string[]
  quantity: number
  use_staff_codes: boolean
  use_flybuys: boolean
  watch_mode: boolean
  status: 'idle' | 'running' | 'success' | 'failed' | 'stopped'
  error_message?: string
  order_number?: string
  created_at: string
  updated_at: string
}

export interface TaskLog {
  id: number
  task_id: string
  level: 'info' | 'warn' | 'error' | 'success'
  message: string
  step: string
  ts: string
}

export interface CsvImportResult {
  imported: number
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status} ${text}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

async function requestText(path: string, options?: RequestInit): Promise<string> {
  const res = await fetch(path, options)
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status} ${text}`)
  }
  return res.text()
}

// ── Profiles ──────────────────────────────────────────────────────────────────
export const api = {
  profiles: {
    list: () => request<Profile[]>('/api/profiles'),
    get: (id: string) => request<Profile>(`/api/profiles/${id}`),
    create: (body: Omit<Profile, 'id' | 'created_at'>) =>
      request<Profile>('/api/profiles', { method: 'POST', body: JSON.stringify(body) }),
    update: (id: string, body: Partial<Profile>) =>
      request<Profile>(`/api/profiles/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    delete: (id: string) => request<void>(`/api/profiles/${id}`, { method: 'DELETE' }),
    exportCsv: () => requestText('/api/profiles/export'),
    importCsv: (csv: string) =>
      request<CsvImportResult>('/api/profiles/import', { method: 'POST', body: JSON.stringify({ csv }) }),
  },

  cards: {
    list: () => request<Card[]>('/api/cards'),
    create: (body: Omit<Card, 'id' | 'created_at'>) =>
      request<Card>('/api/cards', { method: 'POST', body: JSON.stringify(body) }),
    update: (id: string, body: Partial<Card>) =>
      request<Card>(`/api/cards/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    delete: (id: string) => request<void>(`/api/cards/${id}`, { method: 'DELETE' }),
    exportCsv: () => requestText('/api/cards/export'),
    importCsv: (csv: string) =>
      request<CsvImportResult>('/api/cards/import', { method: 'POST', body: JSON.stringify({ csv }) }),
  },

  tasks: {
    list: () => request<Task[]>('/api/tasks'),
    get: (id: string) => request<Task>(`/api/tasks/${id}`),
    create: (body: Omit<Task, 'id' | 'status' | 'created_at' | 'updated_at' | 'error_message' | 'order_number'>) =>
      request<Task>('/api/tasks', { method: 'POST', body: JSON.stringify(body) }),
    update: (id: string, body: Partial<Task>) =>
      request<Task>(`/api/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    delete: (id: string) => request<void>(`/api/tasks/${id}`, { method: 'DELETE' }),
    start: (id: string) => request<Task>(`/api/tasks/${id}/start`, { method: 'POST' }),
    stop: (id: string) => request<Task>(`/api/tasks/${id}/stop`, { method: 'POST' }),
    startAll: () => request<{ started: number }>('/api/tasks/start-all', { method: 'POST' }),
    stopAll: () => request<{ ok: boolean }>('/api/tasks/stop-all', { method: 'POST' }),
    logs: (id: string) => request<TaskLog[]>(`/api/tasks/${id}/logs`),
    exportCsv: () => requestText('/api/tasks/export'),
    importCsv: (csv: string) =>
      request<CsvImportResult>('/api/tasks/import', { method: 'POST', body: JSON.stringify({ csv }) }),
  },

  settings: {
    get: () => request<Record<string, string>>('/api/settings'),
    save: (body: Record<string, string>) =>
      request<Record<string, string>>('/api/settings', { method: 'PUT', body: JSON.stringify(body) }),
  },
}
