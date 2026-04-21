/**
 * Zustand global store.
 * Holds real-time task status map and WebSocket connection state.
 * Task logs are accumulated per task_id.
 */

import { create } from 'zustand'
import type { TaskLog } from '../api/client'

export type TaskStatus = 'idle' | 'running' | 'success' | 'failed' | 'stopped'

export interface TaskState {
  status: TaskStatus
  step: string
  order_number?: string
  error_message?: string
}

interface Store {
  // ws connection
  wsConnected: boolean
  setWsConnected: (v: boolean) => void

  // live task statuses (task_id → state)
  taskStates: Record<string, TaskState>
  setTaskState: (task_id: string, state: Partial<TaskState>) => void

  // per-task log accumulation (task_id → logs[])
  taskLogs: Record<string, TaskLog[]>
  logVersions: Record<string, number>
  appendLog: (log: TaskLog) => void
  clearLogs: (task_id: string) => void
}

export const useStore = create<Store>((set) => ({
  wsConnected: false,
  setWsConnected: (v) => set({ wsConnected: v }),

  taskStates: {},
  setTaskState: (task_id, state) =>
    set((s) => ({
      taskStates: {
        ...s.taskStates,
        [task_id]: { ...s.taskStates[task_id], ...state },
      },
    })),

  taskLogs: {},
  logVersions: {},
  appendLog: (log) =>
    set((s) => {
      const existing = s.taskLogs[log.task_id] ?? []
      // Dedupe against the most recent line — React StrictMode dev double-mount
      // opens two WS connections briefly, so the same event can arrive twice.
      const last = existing[existing.length - 1]
      if (last && last.ts === log.ts && last.message === log.message && last.step === log.step) {
        return {}
      }
      // Keep last 500 lines per task to avoid unbounded growth
      const updated = [...existing, log].slice(-500)
      return { taskLogs: { ...s.taskLogs, [log.task_id]: updated } }
    }),
  clearLogs: (task_id) =>
    set((s) => ({
      taskLogs: { ...s.taskLogs, [task_id]: [] },
      logVersions: {
        ...s.logVersions,
        [task_id]: (s.logVersions[task_id] ?? 0) + 1,
      },
    })),
}))
