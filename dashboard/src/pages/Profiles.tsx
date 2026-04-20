import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2, MapPin, Mail, Phone, Download, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '../api/client'
import type { Profile } from '../api/client'
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
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { downloadCsv } from '@/lib/csv'

const AU_STATES = ['ACT', 'NSW', 'NT', 'QLD', 'SA', 'TAS', 'VIC', 'WA']

const EMPTY: Omit<Profile, 'id' | 'created_at'> = {
  name: '', first_name: '', last_name: '', email: '', mobile: '',
  address1: '', address2: '', city: '', state: 'VIC', postcode: '',
  country: 'AU', flybuys: '',
}

function ProfileDialog({ profile, open, onOpenChange }: { profile?: Profile; open: boolean; onOpenChange: (o: boolean) => void }) {
  const [form, setForm] = useState(profile ? { ...profile } : { ...EMPTY })
  const qc = useQueryClient()

  const set = <K extends keyof typeof form>(k: K) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((p) => ({ ...p, [k]: e.target.value }))

  const createMut = useMutation({
    mutationFn: api.profiles.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['profiles'] }); toast.success('Profile created'); onOpenChange(false) },
    onError: (e: Error) => toast.error(`Create failed: ${e.message}`),
  })
  const updateMut = useMutation({
    mutationFn: ({ id, ...b }: Profile) => api.profiles.update(id, b),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['profiles'] }); toast.success('Profile updated'); onOpenChange(false) },
    onError: (e: Error) => toast.error(`Save failed: ${e.message}`),
  })

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.name) { toast.error('Profile name is required'); return }
    if (profile) updateMut.mutate(form as Profile)
    else createMut.mutate(form)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{profile ? 'Edit profile' : 'New profile'}</DialogTitle>
          <DialogDescription>Shipping and billing info used at checkout.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="name">Profile name<span className="text-red-400"> *</span></Label>
            <Input id="name" value={form.name} onChange={set('name')} placeholder="Home — Jane" required />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>First name</Label>
              <Input value={form.first_name} onChange={set('first_name')} />
            </div>
            <div className="space-y-1.5">
              <Label>Last name</Label>
              <Input value={form.last_name} onChange={set('last_name')} />
            </div>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Email</Label>
              <Input type="email" value={form.email} onChange={set('email')} />
            </div>
            <div className="space-y-1.5">
              <Label>Mobile</Label>
              <Input value={form.mobile} onChange={set('mobile')} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Address line 1</Label>
            <Input value={form.address1} onChange={set('address1')} />
          </div>
          <div className="space-y-1.5">
            <Label>Address line 2</Label>
            <Input value={form.address2} onChange={set('address2')} />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label>City</Label>
              <Input value={form.city} onChange={set('city')} />
            </div>
            <div className="space-y-1.5">
              <Label>State</Label>
              <Select value={form.state} onValueChange={(v) => setForm((f) => ({ ...f, state: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>{AU_STATES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Postcode</Label>
              <Input value={form.postcode} onChange={set('postcode')} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Flybuys number</Label>
            <Input value={form.flybuys} onChange={set('flybuys')} placeholder="Optional" />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={createMut.isPending || updateMut.isPending}>
              {profile ? 'Save changes' : 'Create profile'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function Profiles() {
  const [editing, setEditing] = useState<Profile | undefined>()
  const [deleting, setDeleting] = useState<Profile | undefined>()
  const [open, setOpen] = useState(false)
  const importInputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()

  const { data: profiles = [], isLoading } = useQuery({ queryKey: ['profiles'], queryFn: api.profiles.list })
  const deleteMut = useMutation({
    mutationFn: api.profiles.delete,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['profiles'] }); toast.success('Profile deleted'); setDeleting(undefined) },
    onError: (e: Error) => toast.error(`Delete failed: ${e.message}`),
  })
  const importMut = useMutation({
    mutationFn: api.profiles.importCsv,
    onSuccess: ({ imported }) => {
      qc.invalidateQueries({ queryKey: ['profiles'] })
      toast.success(`Imported ${imported} profile${imported === 1 ? '' : 's'}`)
    },
    onError: (e: Error) => toast.error(`Import failed: ${e.message}`),
  })
  const exportMut = useMutation({
    mutationFn: api.profiles.exportCsv,
    onSuccess: (csv) => {
      downloadCsv('profiles.csv', csv)
      toast.success('Profiles CSV exported')
    },
    onError: (e: Error) => toast.error(`Export failed: ${e.message}`),
  })

  function openNew() { setEditing(undefined); setOpen(true) }
  function openEdit(p: Profile) { setEditing(p); setOpen(true) }
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
        title="Profiles"
        description="Shipping & billing addresses used at checkout"
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => importInputRef.current?.click()} disabled={importMut.isPending}>
              <Upload className="size-3.5" /> Import CSV
            </Button>
            <Button variant="outline" size="sm" onClick={() => exportMut.mutate()} disabled={exportMut.isPending}>
              <Download className="size-3.5" /> Export CSV
            </Button>
            <Button size="sm" onClick={openNew}><Plus className="size-3.5" /> New profile</Button>
          </>
        }
      />
      <div className="px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
        {isLoading ? (
          <div className="text-muted-foreground text-sm">Loading…</div>
        ) : profiles.length === 0 ? (
          <Card>
            <CardContent className="py-16 flex flex-col items-center text-center gap-3">
              <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center">
                <MapPin className="size-5 text-muted-foreground" />
              </div>
              <div>
                <div className="font-medium">No profiles yet</div>
                <div className="text-sm text-muted-foreground mt-0.5">Add a shipping address to use on tasks.</div>
              </div>
              <Button size="sm" onClick={openNew}><Plus className="size-3.5" /> New profile</Button>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {profiles.map((p) => (
              <Card key={p.id} className="gap-0">
                <CardContent className="p-5 space-y-3">
                  <div className="flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="font-medium">{p.name}</div>
                      <div className="text-sm text-muted-foreground truncate">{p.first_name} {p.last_name}</div>
                    </div>
                    <div className="flex shrink-0 gap-1">
                      <Button variant="ghost" size="iconSm" onClick={() => openEdit(p)}><Pencil className="size-3.5" /></Button>
                      <Button variant="ghost" size="iconSm" onClick={() => setDeleting(p)} className="hover:text-red-400"><Trash2 className="size-3.5" /></Button>
                    </div>
                  </div>
                  <div className="space-y-1 text-xs text-muted-foreground">
                    {p.address1 && (
                      <div className="flex items-start gap-2">
                        <MapPin className="size-3 mt-0.5 shrink-0" />
                        <span>{p.address1}{p.address2 ? `, ${p.address2}` : ''}, {p.city} {p.state} {p.postcode}</span>
                      </div>
                    )}
                    {p.email && <div className="flex items-center gap-2"><Mail className="size-3" />{p.email}</div>}
                    {p.mobile && <div className="flex items-center gap-2"><Phone className="size-3" />{p.mobile}</div>}
                    {p.flybuys && <div className="text-blue-400/90">Flybuys · {p.flybuys}</div>}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
      {open && <ProfileDialog profile={editing} open={open} onOpenChange={setOpen} />}
      <AlertDialog open={!!deleting} onOpenChange={(next) => !next && setDeleting(undefined)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete profile?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleting
                ? `This will permanently remove "${deleting.name}" from your saved profiles.`
                : 'This profile will be permanently removed.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteMut.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={!deleting || deleteMut.isPending}
              onClick={() => deleting && deleteMut.mutate(deleting.id)}
            >
              {deleteMut.isPending ? 'Deleting…' : 'Delete profile'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
