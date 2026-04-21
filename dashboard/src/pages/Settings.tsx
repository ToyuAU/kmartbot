import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Save, Webhook, Mail, Shield } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '../api/client'
import { PageHeader } from '../components/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

interface SectionField {
  key: string
  label: string
  placeholder?: string
  description?: string
  type?: 'text' | 'url'
}

const SECTIONS: { title: string; description: string; icon: typeof Webhook; fields: SectionField[] }[] = [
  {
    title: 'Webhooks',
    description: 'Discord webhooks for task notifications and 3DS challenges.',
    icon: Webhook,
    fields: [
      { key: 'webhook_url', label: 'Success / failure webhook', placeholder: 'https://discord.com/api/webhooks/…', type: 'url' },
      { key: 'challenge_webhook_url', label: '3DS challenge webhook', placeholder: 'Leave blank to use main webhook', type: 'url', description: 'Falls back to the main webhook if empty.' },
    ],
  },
  {
    title: 'Email generation',
    description: 'How order emails are generated per task.',
    icon: Mail,
    fields: [
      { key: 'catchall_domain', label: 'Catch-all domain', placeholder: 'yourdomain.com' },
      { key: 'gmail_spoofing_email', label: 'Gmail base address', placeholder: 'you@gmail.com', description: 'Sub-address trick — e.g. you+task1@gmail.com.' },
    ],
  },
]

const TOGGLES: { key: string; label: string; description: string; icon?: typeof Shield }[] = [
  { key: 'use_gmail_spoofing', label: 'Gmail sub-address spoofing', description: 'Use + suffixes on the Gmail base address for each task.', icon: Mail },
  { key: 'use_staff_codes', label: 'Staff discount codes', description: 'Apply a team-member discount at checkout when available.', icon: Shield },
]

export function Settings() {
  const [draft, setDraft] = useState<Record<string, string> | null>(null)
  const qc = useQueryClient()
  const { data: settings } = useQuery({ queryKey: ['settings'], queryFn: api.settings.get })
  const form = draft ?? settings ?? {}

  const saveMut = useMutation({
    mutationFn: api.settings.save,
    onSuccess: (saved) => {
      qc.setQueryData(['settings'], saved)
      setDraft(null)
      toast.success('Settings saved')
    },
    onError: (e: Error) => toast.error(`Save failed: ${e.message}`),
  })

  function updateField(key: string, value: string) {
    setDraft((current) => ({ ...(current ?? settings ?? {}), [key]: value }))
  }

  return (
    <div className="flex-1 min-h-screen">
      <PageHeader
        title="Settings"
        description="Global configuration — persisted to SQLite"
        actions={
          <Button size="sm" onClick={() => saveMut.mutate(form)} disabled={saveMut.isPending} className="w-full sm:w-auto">
            <Save className="size-3.5" /> Save
          </Button>
        }
      />
      <div className="max-w-3xl space-y-5 px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
        {SECTIONS.map((section) => (
          <Card key={section.title}>
            <CardHeader>
              <div className="flex items-center gap-2">
                <div className="h-7 w-7 rounded-md bg-muted flex items-center justify-center">
                  <section.icon className="size-3.5 text-muted-foreground" />
                </div>
                <div>
                  <CardTitle className="text-sm">{section.title}</CardTitle>
                  <CardDescription className="text-xs">{section.description}</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {section.fields.map((f) => (
                <div key={f.key} className="space-y-1.5">
                  <Label htmlFor={f.key}>{f.label}</Label>
                  <Input
                    id={f.key}
                    type={f.type ?? 'text'}
                    value={form[f.key] ?? ''}
                    placeholder={f.placeholder}
                    onChange={(e) => updateField(f.key, e.target.value)}
                  />
                  {f.description && <p className="text-xs text-muted-foreground">{f.description}</p>}
                </div>
              ))}
            </CardContent>
          </Card>
        ))}

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <div className="h-7 w-7 rounded-md bg-muted flex items-center justify-center">
                <Shield className="size-3.5 text-muted-foreground" />
              </div>
              <div>
                <CardTitle className="text-sm">Behavior</CardTitle>
                <CardDescription className="text-xs">Toggles applied globally to all tasks.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {TOGGLES.map((t) => (
              <div key={t.key} className="flex flex-col gap-3 rounded-md border border-border px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
                <div className="pr-4">
                  <div className="text-sm font-medium">{t.label}</div>
                  <div className="text-xs text-muted-foreground">{t.description}</div>
                </div>
                <Switch
                  checked={form[t.key] === 'true'}
                  onCheckedChange={(v) => updateField(t.key, v ? 'true' : 'false')}
                />
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
