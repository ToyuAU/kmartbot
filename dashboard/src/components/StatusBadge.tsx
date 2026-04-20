import { Badge } from '@/components/ui/badge'
import type { TaskStatus } from '../store'
import { cn } from '@/lib/utils'

const CONFIG: Record<TaskStatus, { label: string; variant: 'default' | 'success' | 'destructive' | 'warning' | 'info' | 'muted'; pulse?: boolean }> = {
  idle:    { label: 'Idle',    variant: 'muted' },
  running: { label: 'Running', variant: 'info', pulse: true },
  success: { label: 'Success', variant: 'success' },
  failed:  { label: 'Failed',  variant: 'destructive' },
  stopped: { label: 'Stopped', variant: 'warning' },
}

export function StatusBadge({ status }: { status: TaskStatus }) {
  const { label, variant, pulse } = CONFIG[status] ?? CONFIG.idle
  return (
    <Badge variant={variant} className={cn('gap-1.5', pulse && 'animate-pulse')}>
      <span className={cn(
        'h-1.5 w-1.5 rounded-full',
        variant === 'info' && 'bg-blue-400',
        variant === 'success' && 'bg-green-400',
        variant === 'destructive' && 'bg-red-400',
        variant === 'warning' && 'bg-yellow-400',
        variant === 'muted' && 'bg-muted-foreground',
      )} />
      {label}
    </Badge>
  )
}
