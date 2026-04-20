import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, CreditCard as CreditCardIcon, Download, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '../api/client'
import type { Card as CardType } from '../api/client'
import { PageHeader } from '../components/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { downloadCsv } from '@/lib/csv'

const EMPTY: Omit<CardType, 'id' | 'created_at'> = {
  alias: '', cardholder: '', number: '', expiry_month: '', expiry_year: '', cvv: '',
}

function detectBrand(number: string): string {
  const n = number.replace(/\s+/g, '')
  if (/^4/.test(n)) return 'Visa'
  if (/^(5[1-5]|2[2-7])/.test(n)) return 'Mastercard'
  if (/^3[47]/.test(n)) return 'Amex'
  return 'Card'
}

function CardDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [form, setForm] = useState({ ...EMPTY })
  const qc = useQueryClient()

  const set = <K extends keyof typeof form>(k: K) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((p) => ({ ...p, [k]: e.target.value }))

  const createMut = useMutation({
    mutationFn: api.cards.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cards'] }); toast.success('Card added'); onOpenChange(false); setForm({ ...EMPTY }) },
    onError: (e: Error) => toast.error(`Add failed: ${e.message}`),
  })

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.alias || !form.number) { toast.error('Alias and number are required'); return }
    createMut.mutate(form)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add card</DialogTitle>
          <DialogDescription>Stored locally in your SQLite database.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <Label>Alias<span className="text-red-400"> *</span></Label>
            <Input value={form.alias} onChange={set('alias')} placeholder="My Revolut card" required />
          </div>
          <div className="space-y-1.5">
            <Label>Cardholder name</Label>
            <Input value={form.cardholder} onChange={set('cardholder')} />
          </div>
          <div className="space-y-1.5">
            <Label>Card number<span className="text-red-400"> *</span></Label>
            <Input value={form.number} onChange={set('number')} placeholder="4111 1111 1111 1111" className="font-mono" required inputMode="numeric" />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label>Month</Label>
              <Input value={form.expiry_month} onChange={set('expiry_month')} placeholder="12" className="font-mono" required />
            </div>
            <div className="space-y-1.5">
              <Label>Year</Label>
              <Input value={form.expiry_year} onChange={set('expiry_year')} placeholder="27" className="font-mono" required />
            </div>
            <div className="space-y-1.5">
              <Label>CVV</Label>
              <Input value={form.cvv} onChange={set('cvv')} placeholder="123" className="font-mono" required />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={createMut.isPending}>Add card</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function Cards() {
  const [open, setOpen] = useState(false)
  const importInputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()
  const { data: cards = [], isLoading } = useQuery({ queryKey: ['cards'], queryFn: api.cards.list })
  const deleteMut = useMutation({
    mutationFn: api.cards.delete,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cards'] }); toast.success('Card deleted') },
    onError: (e: Error) => toast.error(`Delete failed: ${e.message}`),
  })
  const importMut = useMutation({
    mutationFn: api.cards.importCsv,
    onSuccess: ({ imported }) => {
      qc.invalidateQueries({ queryKey: ['cards'] })
      toast.success(`Imported ${imported} card${imported === 1 ? '' : 's'}`)
    },
    onError: (e: Error) => toast.error(`Import failed: ${e.message}`),
  })
  const exportMut = useMutation({
    mutationFn: api.cards.exportCsv,
    onSuccess: (csv) => {
      downloadCsv('cards.csv', csv)
      toast.success('Cards CSV exported')
    },
    onError: (e: Error) => toast.error(`Export failed: ${e.message}`),
  })

  function confirmDelete(c: CardType) {
    toast(`Delete "${c.alias}"?`, {
      action: { label: 'Delete', onClick: () => deleteMut.mutate(c.id) },
      cancel: { label: 'Cancel', onClick: () => {} },
    })
  }
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
      <PageHeader
        title="Cards"
        description="Payment cards available to tasks"
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => importInputRef.current?.click()} disabled={importMut.isPending}>
              <Upload className="size-3.5" /> Import CSV
            </Button>
            <Button variant="outline" size="sm" onClick={() => exportMut.mutate()} disabled={exportMut.isPending}>
              <Download className="size-3.5" /> Export CSV
            </Button>
            <Button size="sm" onClick={() => setOpen(true)}><Plus className="size-3.5" /> Add card</Button>
          </>
        }
      />
      <div className="px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
        {isLoading ? (
          <div className="text-muted-foreground text-sm">Loading…</div>
        ) : cards.length === 0 ? (
          <Card>
            <CardContent className="py-16 flex flex-col items-center text-center gap-3">
              <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center">
                <CreditCardIcon className="size-5 text-muted-foreground" />
              </div>
              <div>
                <div className="font-medium">No cards yet</div>
                <div className="text-sm text-muted-foreground mt-0.5">Add a card to use on tasks.</div>
              </div>
              <Button size="sm" onClick={() => setOpen(true)}><Plus className="size-3.5" /> Add card</Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {cards.map((c) => (
              <Card key={c.id} className="gap-0 overflow-hidden">
                <CardContent className="p-5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="text-xs uppercase tracking-wider text-muted-foreground">{detectBrand(c.number)}</div>
                      <div className="font-medium mt-0.5 truncate">{c.alias}</div>
                    </div>
                    <Button variant="ghost" size="iconSm" onClick={() => confirmDelete(c)} className="hover:text-red-400">
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                  <div className="mt-4 font-mono text-sm tracking-wider text-foreground/90">
                    •••• •••• •••• {c.number.slice(-4)}
                  </div>
                  <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
                    <span className="truncate">{c.cardholder || '—'}</span>
                    <span className="font-mono">{c.expiry_month}/{c.expiry_year}</span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
      {open && <CardDialog open={open} onOpenChange={setOpen} />}
    </div>
  )
}
