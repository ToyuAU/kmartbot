import { useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Play, Square, Search, Inbox, Download, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '../api/client'
import type { Task } from '../api/client'
import { TaskCard } from '../components/TaskCard'
import { TaskForm } from '../components/TaskForm'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { useStore } from '../store'
import { downloadCsv } from '@/lib/csv'

function Stat({ label, value, tone }: { label: string; value: number; tone?: 'default' | 'info' | 'success' | 'destructive' | 'muted' }) {
  const tones: Record<string, string> = {
    default: 'text-foreground',
    info: 'text-blue-400',
    success: 'text-green-400',
    destructive: 'text-red-400',
    muted: 'text-muted-foreground',
  }
  return (
    <Card className="gap-0">
      <CardContent className="px-5 py-4">
        <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
        <div className={`mt-1 text-2xl font-semibold tabular-nums ${tones[tone ?? 'default']}`}>{value}</div>
      </CardContent>
    </Card>
  )
}

export function Tasks() {
  const [editTask, setEditTask] = useState<Task | undefined>()
  const [formOpen, setFormOpen] = useState(false)
  const [query, setQuery] = useState('')
  const importInputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()
  const taskStates = useStore((s) => s.taskStates)

  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ['tasks'],
    queryFn: api.tasks.list,
    refetchInterval: 5000,
  })

  const startAll = useMutation({
    mutationFn: api.tasks.startAll,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); toast.success('Starting all eligible tasks') },
    onError: (e: Error) => toast.error(`Start all failed: ${e.message}`),
  })
  const stopAll = useMutation({
    mutationFn: api.tasks.stopAll,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); toast.info('Stopping all running tasks') },
    onError: (e: Error) => toast.error(`Stop all failed: ${e.message}`),
  })
  const importMut = useMutation({
    mutationFn: api.tasks.importCsv,
    onSuccess: ({ imported }) => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success(`Imported ${imported} task${imported === 1 ? '' : 's'}`)
    },
    onError: (e: Error) => toast.error(`Import failed: ${e.message}`),
  })
  const exportMut = useMutation({
    mutationFn: api.tasks.exportCsv,
    onSuccess: (csv) => {
      downloadCsv('tasks.csv', csv)
      toast.success('Tasks CSV exported')
    },
    onError: (e: Error) => toast.error(`Export failed: ${e.message}`),
  })

  const statuses = useMemo(() => tasks.map(t => taskStates[t.id]?.status ?? t.status), [tasks, taskStates])
  const counts = useMemo(() => ({
    total: tasks.length,
    running: statuses.filter(s => s === 'running').length,
    success: statuses.filter(s => s === 'success').length,
    failed: statuses.filter(s => s === 'failed').length,
  }), [tasks.length, statuses])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return tasks
    return tasks.filter((t) =>
      t.name.toLowerCase().includes(q) ||
      t.sku.toLowerCase().includes(q) ||
      (t.order_number ?? '').toLowerCase().includes(q)
    )
  }, [tasks, query])

  function openNew() { setEditTask(undefined); setFormOpen(true) }
  function openEdit(t: Task) { setEditTask(t); setFormOpen(true) }
  async function handleImportChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    importMut.mutate(await file.text())
  }

  return (
    <div className="flex-1 min-h-screen">
      <input
        ref={importInputRef}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={handleImportChange}
      />
      <header className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur-xl">
        <div className="flex min-h-14 flex-col gap-3 px-4 py-3 sm:px-6 lg:px-8 md:flex-row md:items-center md:gap-4">
          <div className="min-w-0">
            <h1 className="text-base font-semibold">Tasks</h1>
          </div>
          <div className="flex w-full flex-col gap-2 md:ml-auto md:w-auto md:flex-row md:items-center md:justify-end">
            <div className="relative w-full md:w-auto">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search tasks…"
                className="h-9 w-full pl-8 md:h-8 md:w-64"
              />
            </div>
            <div className="grid grid-cols-2 gap-2 md:flex md:flex-wrap md:items-center">
              <Button
                variant="outline"
                size="sm"
                onClick={() => startAll.mutate()}
                disabled={startAll.isPending}
                className="w-full border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 hover:text-emerald-300 md:w-auto"
              >
                <Play className="size-3.5" /> Start all
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => stopAll.mutate()}
                disabled={counts.running === 0 || stopAll.isPending}
                className="w-full border-red-500/30 text-red-400 hover:bg-red-500/10 hover:text-red-300 md:w-auto"
              >
                <Square className="size-3.5" /> Stop all
              </Button>
              <Button variant="outline" size="sm" onClick={() => importInputRef.current?.click()} disabled={importMut.isPending} className="w-full md:w-auto">
                <Upload className="size-3.5" /> Import CSV
              </Button>
              <Button variant="outline" size="sm" onClick={() => exportMut.mutate()} disabled={exportMut.isPending} className="w-full md:w-auto">
                <Download className="size-3.5" /> Export CSV
              </Button>
              <Button size="sm" onClick={openNew} className="w-full md:w-auto">
                <Plus className="size-3.5" /> New task
              </Button>
            </div>
          </div>
        </div>
      </header>

      <div className="space-y-6 px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label="Total" value={counts.total} />
          <Stat label="Running" value={counts.running} tone="info" />
          <Stat label="Success" value={counts.success} tone="success" />
          <Stat label="Failed" value={counts.failed} tone="destructive" />
        </div>

        {isLoading ? (
          <div className="text-muted-foreground text-sm">Loading…</div>
        ) : tasks.length === 0 ? (
          <Card>
            <CardContent className="py-16 flex flex-col items-center text-center gap-3">
              <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center">
                <Inbox className="size-5 text-muted-foreground" />
              </div>
              <div>
                <div className="font-medium">No tasks yet</div>
                <div className="text-sm text-muted-foreground mt-0.5">Create your first checkout task to get started.</div>
              </div>
              <Button size="sm" onClick={openNew}><Plus className="size-3.5" /> New task</Button>
            </CardContent>
          </Card>
        ) : filtered.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground text-sm">No tasks match "{query}".</div>
        ) : (
          <div className="space-y-2">
            {filtered.map((task) => (
              <TaskCard key={task.id} task={task} onEdit={openEdit} />
            ))}
          </div>
        )}
      </div>

      {formOpen && (
        <TaskForm
          key={editTask?.id ?? 'new-task'}
          task={editTask}
          open={formOpen}
          onOpenChange={setFormOpen}
        />
      )}
    </div>
  )
}
