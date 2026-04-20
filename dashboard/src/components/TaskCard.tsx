import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, Play, Square, Trash2, Pencil } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '../api/client'
import type { Task } from '../api/client'
import { StatusBadge } from './StatusBadge'
import { LogStream } from './LogStream'
import { useStore } from '../store'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

interface Props {
  task: Task
  onEdit: (task: Task) => void
}

export function TaskCard({ task, onEdit }: Props) {
  const [logsOpen, setLogsOpen] = useState(false)
  const qc = useQueryClient()
  const liveState = useStore((s) => s.taskStates[task.id])
  const status = liveState?.status ?? task.status
  const step = liveState?.step ?? ''
  const orderNumber = liveState?.order_number ?? task.order_number
  const errorMessage = liveState?.error_message ?? task.error_message

  const startMut = useMutation({
    mutationFn: () => api.tasks.start(task.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); toast.success(`Started ${task.name || task.sku}`) },
    onError: (e: Error) => toast.error(`Failed to start: ${e.message}`),
  })
  const stopMut = useMutation({
    mutationFn: () => api.tasks.stop(task.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); toast.info(`Stopped ${task.name || task.sku}`) },
    onError: (e: Error) => toast.error(`Failed to stop: ${e.message}`),
  })
  const deleteMut = useMutation({
    mutationFn: () => api.tasks.delete(task.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); toast.success('Task deleted') },
    onError: (e: Error) => toast.error(`Delete failed: ${e.message}`),
  })

  const isRunning = status === 'running'

  return (
    <div className={cn(
      'rounded-lg border border-border bg-card transition-colors',
      isRunning && 'ring-1 ring-blue-500/30'
    )}>
      <div className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          <StatusBadge status={status} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
              <span className="truncate font-medium text-foreground">{task.name || `SKU ${task.sku}`}</span>
              <span className="hidden text-xs font-mono text-muted-foreground sm:inline">·</span>
              <span className="text-xs font-mono text-muted-foreground">{task.sku}</span>
              {task.quantity > 1 && (
                <span className="text-xs text-muted-foreground">× {task.quantity}</span>
              )}
            </div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              {isRunning && step
                ? <span className="text-blue-400">{step.replace(/_/g, ' ').toLowerCase()}</span>
                : orderNumber
                  ? <span className="text-green-400">Order {orderNumber}</span>
                  : status === 'failed' && errorMessage
                    ? <span className="block text-red-400">{errorMessage}</span>
                    : <span>{task.site}</span>
              }
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1 sm:shrink-0 sm:justify-end">
          {isRunning ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="destructive" size="iconSm" onClick={() => stopMut.mutate()} disabled={stopMut.isPending}>
                  <Square className="size-3.5" fill="currentColor" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Stop task</TooltipContent>
            </Tooltip>
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="secondary" size="iconSm" onClick={() => startMut.mutate()} disabled={startMut.isPending}>
                  <Play className="size-3.5" fill="currentColor" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>Start task</TooltipContent>
            </Tooltip>
          )}

          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="iconSm" onClick={() => onEdit(task)}>
                <Pencil className="size-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Edit</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="iconSm" onClick={() => deleteMut.mutate()} className="hover:text-red-400">
                <Trash2 className="size-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Delete</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="iconSm"
                onClick={() => setLogsOpen(v => !v)}
                className={cn(logsOpen && 'bg-accent')}
              >
                <ChevronDown className={cn('size-4 transition-transform', logsOpen && 'rotate-180')} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{logsOpen ? 'Hide logs' : 'Show logs'}</TooltipContent>
          </Tooltip>
        </div>
      </div>

      {logsOpen && <LogStream taskId={task.id} />}
    </div>
  )
}
