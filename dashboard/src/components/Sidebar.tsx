import { NavLink } from 'react-router-dom'
import { LayoutDashboard, CreditCard, User, Settings } from 'lucide-react'
import { useStore } from '../store'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/',         icon: LayoutDashboard, label: 'Tasks' },
  { to: '/profiles', icon: User,            label: 'Profiles' },
  { to: '/cards',    icon: CreditCard,      label: 'Cards' },
  { to: '/settings', icon: Settings,        label: 'Settings' },
]

export function Sidebar() {
  const wsConnected = useStore((s) => s.wsConnected)

  return (
    <>
      <aside className="hidden w-56 shrink-0 border-r border-border bg-card/30 md:sticky md:top-0 md:flex md:h-dvh md:self-start md:flex-col md:overflow-hidden">
        <div className="flex h-14 items-center gap-2 border-b border-border px-5">
          <img src="/logo.png" alt="Nova AIO logo" className="h-5 w-5 rounded-md object-contain" />
          <span className="font-semibold tracking-tight">Nova AIO</span>
          <span className="ml-auto text-[10px] uppercase tracking-wider text-muted-foreground">v1.0.0</span>
        </div>

        <nav className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 py-3">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                cn(
                  'flex h-9 items-center gap-2.5 rounded-md px-3 text-sm transition-colors',
                  isActive
                    ? 'bg-accent font-medium text-foreground'
                    : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground'
                )
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <span className={cn('relative flex h-2 w-2', wsConnected ? '' : 'opacity-60')}>
              <span className={cn('absolute inline-flex h-full w-full rounded-full opacity-75', wsConnected && 'animate-ping bg-green-500')} />
              <span className={cn('relative inline-flex h-2 w-2 rounded-full', wsConnected ? 'bg-green-500' : 'bg-muted-foreground')} />
            </span>
            <span className="text-xs text-muted-foreground">{wsConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
        </div>
      </aside>

      <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-card/95 backdrop-blur-xl md:hidden">
        <div className="grid grid-cols-4 gap-1 px-2 py-2 [padding-bottom:calc(0.5rem+env(safe-area-inset-bottom))]">
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                cn(
                  'flex min-h-14 flex-col items-center justify-center gap-1 rounded-lg px-1 text-[11px] font-medium transition-colors',
                  isActive
                    ? 'bg-accent text-foreground'
                    : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground'
                )
              }
            >
              <span className="relative flex items-center justify-center">
                <Icon size={18} />
                {to === '/' && (
                  <span className={cn(
                    'absolute -right-1.5 -top-1.5 h-2 w-2 rounded-full',
                    wsConnected ? 'bg-green-500' : 'bg-muted-foreground'
                  )} />
                )}
              </span>
              <span>{label}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </>
  )
}
