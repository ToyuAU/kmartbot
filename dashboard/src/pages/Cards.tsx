import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Pencil, CreditCard as CreditCardIcon, Download, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '../api/client'
import type { Card as CardType } from '../api/client'
import { PageHeader } from '../components/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { downloadCsv } from '@/lib/csv'

const EMPTY: Omit<CardType, 'id' | 'created_at'> = {
  alias: '', cardholder: '', number: '', expiry_month: '', expiry_year: '', cvv: '',
}

type Brand = 'Visa' | 'Mastercard' | 'Amex' | 'Card'

function detectBrand(number: string): Brand {
  const n = number.replace(/\s+/g, '')
  if (/^4/.test(n)) return 'Visa'
  if (/^(5[1-5]|2[2-7])/.test(n)) return 'Mastercard'
  if (/^3[47]/.test(n)) return 'Amex'
  return 'Card'
}

const BRAND_STYLES: Record<Brand, string> = {
  Visa: 'bg-gradient-to-br from-indigo-900/80 via-blue-950/80 to-slate-950',
  Mastercard: 'bg-gradient-to-br from-zinc-900 via-zinc-950 to-black',
  Amex: 'bg-gradient-to-br from-sky-900/80 via-cyan-950/80 to-slate-950',
  Card: 'bg-gradient-to-br from-slate-800 via-slate-900 to-slate-950',
}

function BrandLogo({ brand }: { brand: Brand }) {
  if (brand === 'Visa') {
    return (
      <svg viewBox="0 0 64 20" className="h-4 w-auto" aria-label="Visa">
        <text x="0" y="16" fontFamily="Helvetica, Arial, sans-serif" fontWeight="900" fontStyle="italic" fontSize="20" fill="#fff" letterSpacing="-1">VISA</text>
      </svg>
    )
  }
  if (brand === 'Mastercard') {
    return (
      <svg viewBox="0 0 40 24" className="h-5 w-auto" aria-label="Mastercard">
        <circle cx="15" cy="12" r="9" fill="#EB001B" />
        <circle cx="25" cy="12" r="9" fill="#F79E1B" fillOpacity="0.9" />
        <path d="M20 5.4a9 9 0 010 13.2 9 9 0 010-13.2z" fill="#FF5F00" />
      </svg>
    )
  }
  if (brand === 'Amex') {
    return (
      <svg viewBox="0 0 52 20" className="h-4 w-auto" aria-label="American Express">
        <rect width="52" height="20" rx="2" fill="#2E77BC" />
        <text x="26" y="14" textAnchor="middle" fontFamily="Helvetica, Arial, sans-serif" fontWeight="800" fontSize="8" fill="#fff" letterSpacing="0.5">AMEX</text>
      </svg>
    )
  }
  return <CreditCardIcon className="size-4 text-white/80" />
}

function Chip() {
  return (
    <svg viewBox="0 0 40 30" className="h-5 w-7" aria-hidden>
      <defs>
        <linearGradient id="chipGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#E8D28A" />
          <stop offset="50%" stopColor="#C9A55C" />
          <stop offset="100%" stopColor="#8E6F2E" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="40" height="30" rx="5" fill="url(#chipGrad)" />
      <path d="M0 10h12M0 20h12M28 10h12M28 20h12M12 0v30M28 0v30" stroke="#7a5a20" strokeWidth="0.6" opacity="0.5" />
      <rect x="12" y="8" width="16" height="14" rx="2" fill="none" stroke="#7a5a20" strokeWidth="0.6" opacity="0.5" />
    </svg>
  )
}

function formatCardNumber(n: string) {
  const last4 = n.replace(/\s+/g, '').slice(-4).padStart(4, '•')
  return `•••• •••• •••• ${last4}`
}

function CardDialog({ card, open, onOpenChange }: { card?: CardType; open: boolean; onOpenChange: (o: boolean) => void }) {
  const isEdit = !!card
  const [form, setForm] = useState(card ? {
    alias: card.alias,
    cardholder: card.cardholder,
    number: card.number,
    expiry_month: card.expiry_month,
    expiry_year: card.expiry_year,
    cvv: card.cvv,
  } : { ...EMPTY })
  const qc = useQueryClient()

  const set = <K extends keyof typeof form>(k: K) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((p) => ({ ...p, [k]: e.target.value }))

  const createMut = useMutation({
    mutationFn: api.cards.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cards'] }); toast.success('Card added'); onOpenChange(false); setForm({ ...EMPTY }) },
    onError: (e: Error) => toast.error(`Add failed: ${e.message}`),
  })
  const updateMut = useMutation({
    mutationFn: (body: typeof form) => api.cards.update(card!.id, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cards'] }); toast.success('Card updated'); onOpenChange(false) },
    onError: (e: Error) => toast.error(`Update failed: ${e.message}`),
  })

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.alias || !form.number) { toast.error('Alias and number are required'); return }
    if (isEdit) updateMut.mutate(form)
    else createMut.mutate(form)
  }

  const pending = createMut.isPending || updateMut.isPending

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit card' : 'Add card'}</DialogTitle>
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
            <Button type="submit" disabled={pending}>{isEdit ? 'Save changes' : 'Add card'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function Cards() {
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState<CardType | undefined>()
  const [deleting, setDeleting] = useState<CardType | undefined>()
  const importInputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()
  const { data: cards = [], isLoading } = useQuery({ queryKey: ['cards'], queryFn: api.cards.list })
  const deleteMut = useMutation({
    mutationFn: api.cards.delete,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['cards'] }); toast.success('Card deleted'); setDeleting(undefined) },
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
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {cards.map((c) => {
              const brand = detectBrand(c.number)
              return (
                <div key={c.id} className="group relative">
                  <div
                    className={`relative aspect-[1.7/1] w-full overflow-hidden rounded-xl p-3.5 text-white shadow-sm ring-1 ring-white/10 ${BRAND_STYLES[brand]}`}
                  >
                    <div className="pointer-events-none absolute -right-12 -top-12 h-32 w-32 rounded-full bg-white/5 blur-2xl" />

                    <div className="relative flex h-full flex-col justify-between">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 truncate text-xs font-medium text-white/90">{c.alias}</div>
                        <BrandLogo brand={brand} />
                      </div>

                      <div className="flex items-center gap-2">
                        <Chip />
                        <div className="flex-1 truncate font-mono text-[13px] tracking-[0.15em] text-white/90">
                          {formatCardNumber(c.number)}
                        </div>
                      </div>

                      <div className="flex items-end justify-between gap-2 text-[10px] text-white/70">
                        <span className="truncate">{c.cardholder || '—'}</span>
                        <span className="font-mono">{c.expiry_month}/{c.expiry_year}</span>
                      </div>
                    </div>
                  </div>
                  <div className="absolute right-1.5 top-1.5 flex gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                    <Button
                      variant="ghost"
                      size="iconSm"
                      onClick={() => setEditing(c)}
                      aria-label="Edit card"
                      className="size-6 text-white/70 hover:bg-white/15 hover:text-white"
                    >
                      <Pencil className="size-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="iconSm"
                      onClick={() => setDeleting(c)}
                      aria-label="Delete card"
                      className="size-6 text-white/70 hover:bg-white/15 hover:text-white"
                    >
                      <Trash2 className="size-3" />
                    </Button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
      {open && <CardDialog open={open} onOpenChange={setOpen} />}
      {editing && (
        <CardDialog
          key={editing.id}
          card={editing}
          open={!!editing}
          onOpenChange={(next) => !next && setEditing(undefined)}
        />
      )}
      <AlertDialog open={!!deleting} onOpenChange={(next) => !next && setDeleting(undefined)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete card?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleting
                ? `This will permanently remove "${deleting.alias}" from your saved cards.`
                : 'This card will be permanently removed.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMut.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={!deleting || deleteMut.isPending}
              onClick={() => deleting && deleteMut.mutate(deleting.id)}
            >
              {deleteMut.isPending ? 'Deleting…' : 'Delete card'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
