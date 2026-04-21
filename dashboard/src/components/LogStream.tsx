import { useEffect, useMemo, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
import { useStore } from '../store'
import type { TaskLog } from '../api/client'
import { cn } from '@/lib/utils'

const LEVEL_CLASS: Record<string, string> = {
  info:    'text-foreground/90',
  warn:    'text-yellow-400',
  error:   'text-red-400',
  success: 'text-green-400',
}

function LogLine({ log }: { log: TaskLog }) {
  const time = new Date(log.ts).toLocaleTimeString('en-AU', { hour12: false })
  return (
    <div className="font-mono text-[11px] leading-5 sm:flex sm:gap-3">
      <div className="flex shrink-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] uppercase tracking-wide text-muted-foreground/70 sm:text-[11px] sm:tracking-normal">
        <span>{time}</span>
        {log.step && <span className="max-w-full truncate text-blue-400/80 sm:w-28">{log.step}</span>}
      </div>
      <div className={cn('break-all sm:min-w-0 sm:flex-1', LEVEL_CLASS[log.level] ?? 'text-foreground/90')}>{log.message}</div>
    </div>
  )
}

const EMPTY: TaskLog[] = []

export function LogStream({ taskId }: { taskId: string }) {
  const liveLogs = useStore((s) => s.taskLogs[taskId]) ?? EMPTY
  const logVersion = useStore((s) => s.logVersions[taskId] ?? 0)
  const bottomRef = useRef<HTMLDivElement>(null)
  const { data: persistedLogs = EMPTY, isLoading } = useQuery({
    queryKey: ['task-logs', taskId, logVersion],
    queryFn: () => api.tasks.logs(taskId),
    staleTime: 0,
  })

  const logs = useMemo(() => {
    const deduped: TaskLog[] = []
    const seen = new Set<string>()
    for (const log of [...persistedLogs, ...liveLogs]) {
      const key = `${log.ts}|${log.step}|${log.level}|${log.message}`
      if (seen.has(key)) continue
      seen.add(key)
      deduped.push(log)
    }
    return deduped
  }, [liveLogs, persistedLogs])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs.length])

  return (
    <div className="border-t border-border bg-background/50">
      <div className="max-h-64 space-y-1 overflow-y-auto px-4 py-2.5">
        {isLoading && logs.length === 0 ? (
          <div className="text-muted-foreground text-xs py-2">Loading logs…</div>
        ) : logs.length === 0 ? (
          <div className="text-muted-foreground text-xs py-2">Waiting for logs…</div>
        ) : (
          logs.map((log) => <LogLine key={`${log.id}-${log.ts}-${log.message}`} log={log} />)
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
