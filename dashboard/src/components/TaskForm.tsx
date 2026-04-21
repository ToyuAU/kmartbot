import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '../api/client'
import type { Task } from '../api/client'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'

interface Props {
  task?: Task
  open: boolean
  onOpenChange: (open: boolean) => void
}

const EMPTY: Omit<Task, 'id' | 'status' | 'created_at' | 'updated_at' | 'error_message' | 'order_number'> = {
  name: '',
  site: 'kmart',
  sku: '',
  profile_id: '',
  card_ids: [],
  quantity: 1,
  use_staff_codes: true,
  use_flybuys: true,
  watch_mode: true,
}

export function TaskForm({ task, open, onOpenChange }: Props) {
  const [form, setForm] = useState(task ? { ...task, card_ids: task.card_ids.slice(0, 1) } : { ...EMPTY })
  const qc = useQueryClient()

  const { data: profiles = [] } = useQuery({ queryKey: ['profiles'], queryFn: api.profiles.list })
  const { data: cards = [] } = useQuery({ queryKey: ['cards'], queryFn: api.cards.list })

  const createMut = useMutation({
    mutationFn: api.tasks.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Task created')
      onOpenChange(false)
    },
    onError: (e: Error) => toast.error(`Failed to create: ${e.message}`),
  })
  const updateMut = useMutation({
    mutationFn: ({ id, ...body }: Task) => api.tasks.update(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tasks'] })
      toast.success('Task updated')
      onOpenChange(false)
    },
    onError: (e: Error) => toast.error(`Failed to save: ${e.message}`),
  })

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.sku || !form.profile_id || form.card_ids.length !== 1) {
      toast.error('SKU, profile, and one card are required')
      return
    }
    if (task) updateMut.mutate(form as Task)
    else createMut.mutate(form)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{task ? 'Edit task' : 'New task'}</DialogTitle>
          <DialogDescription>
            {task ? 'Update task configuration.' : 'Configure a new checkout task.'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="name">Name</Label>
              <Input id="name" placeholder="Optional" value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sku">SKU<span className="text-red-400"> *</span></Label>
              <Input id="sku" placeholder="43675449" required value={form.sku} onChange={(e) => setForm((f) => ({ ...f, sku: e.target.value }))} />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Profile<span className="text-red-400"> *</span></Label>
              <Select value={form.profile_id} onValueChange={(v) => setForm((f) => ({ ...f, profile_id: v }))}>
                <SelectTrigger>
                  <SelectValue placeholder="Select profile…" />
                </SelectTrigger>
                <SelectContent>
                  {profiles.length === 0 && <div className="px-2 py-1.5 text-xs text-muted-foreground">No profiles — add one first.</div>}
                  {profiles.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="quantity">Quantity</Label>
              <Input id="quantity" type="number" min={1} max={100} value={form.quantity} onChange={(e) => setForm((f) => ({ ...f, quantity: Number(e.target.value) }))} />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Card<span className="text-red-400"> *</span></Label>
            <Select
              value={form.card_ids[0] ?? ''}
              onValueChange={(value) => setForm((f) => ({ ...f, card_ids: value ? [value] : [] }))}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select card…" />
              </SelectTrigger>
              <SelectContent>
                {cards.length === 0 && <div className="px-2 py-1.5 text-xs text-muted-foreground">No cards — add one first.</div>}
                {cards.map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.alias} · •••• {c.number.slice(-4)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-3 rounded-md border border-border px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
            <div className="pr-4">
              <div className="text-sm font-medium">Staff discount codes</div>
              <div className="text-xs text-muted-foreground">Apply a team member discount</div>
            </div>
            <Switch checked={form.use_staff_codes} onCheckedChange={(v) => setForm((f) => ({ ...f, use_staff_codes: v }))} />
          </div>

          <div className="flex flex-col gap-3 rounded-md border border-border px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
            <div className="pr-4">
              <div className="text-sm font-medium">Flybuys</div>
              <div className="text-xs text-muted-foreground">Attach the profile's Flybuys number</div>
            </div>
            <Switch checked={form.use_flybuys} onCheckedChange={(v) => setForm((f) => ({ ...f, use_flybuys: v }))} />
          </div>

          <div className="flex flex-col gap-3 rounded-md border border-border px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
            <div className="pr-4">
              <div className="text-sm font-medium">Watch mode</div>
              <div className="text-xs text-muted-foreground">
                Continuously monitor for product availability.
              </div>
            </div>
            <Switch checked={form.watch_mode} onCheckedChange={(v) => setForm((f) => ({ ...f, watch_mode: v }))} />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={createMut.isPending || updateMut.isPending}>
              {task ? 'Save changes' : 'Create task'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
