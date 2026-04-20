import type { ReactNode } from 'react'

interface Props {
  title: string
  description?: string
  actions?: ReactNode
}

export function PageHeader({ title, description, actions }: Props) {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur-xl">
      <div className="flex min-h-14 flex-col gap-3 px-4 py-3 sm:px-6 lg:px-8 md:flex-row md:items-center md:gap-4">
        <div className="min-w-0">
          <h1 className="text-base font-semibold">{title}</h1>
          {description && <p className="text-xs text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2 md:ml-auto md:justify-end">{actions}</div>}
      </div>
    </header>
  )
}
