import { useEffect, useRef } from 'react'
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
  const logs = useStore((s) => s.taskLogs[taskId]) ?? EMPTY
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs.length])

  return (
    <div className="border-t border-border bg-background/50">
      <div className="max-h-64 space-y-1 overflow-y-auto px-4 py-2.5">
        {logs.length === 0 ? (
          <div className="text-muted-foreground text-xs py-2">Waiting for logs…</div>
        ) : (
          logs.map((log) => <LogLine key={log.id} log={log} />)
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
