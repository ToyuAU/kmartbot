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
import { Checkbox } from '@/components/ui/checkbox'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'

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
  const [form, setForm] = useState(task ? { ...task } : { ...EMPTY })
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

  function toggleCard(cardId: string) {
    setForm((f) => ({
      ...f,
      card_ids: f.card_ids.includes(cardId)
        ? f.card_ids.filter((c) => c !== cardId)
        : [...f.card_ids, cardId],
    }))
  }

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.sku || !form.profile_id) {
      toast.error('SKU and profile are required')
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
            <div className="flex items-center justify-between">
              <Label>Cards</Label>
              {cards.length > 0 && (
                <button
                  type="button"
                  onClick={() =>
                    setForm((f) => ({
                      ...f,
                      card_ids: f.card_ids.length === cards.length ? [] : cards.map((c) => c.id),
                    }))
                  }
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  {form.card_ids.length === cards.length ? 'Deselect all' : 'Select all'}
                </button>
              )}
            </div>
            <div className="rounded-md border border-border divide-y divide-border max-h-40 overflow-y-auto">
              {cards.length === 0 ? (
                <div className="px-3 py-2.5 text-xs text-muted-foreground">No cards — add some in Cards.</div>
              ) : cards.map((c) => {
                const checked = form.card_ids.includes(c.id)
                return (
                  <label key={c.id} className={cn('flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-accent/50 transition-colors', checked && 'bg-accent/40')}>
                    <Checkbox checked={checked} onCheckedChange={() => toggleCard(c.id)} />
                    <span className="text-sm">{c.alias}</span>
                    <span className="ml-auto text-xs text-muted-foreground font-mono">•••• {c.number.slice(-4)}</span>
                  </label>
                )
              })}
            </div>
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
