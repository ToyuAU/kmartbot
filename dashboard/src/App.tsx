import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Sidebar } from './components/Sidebar'
import { Tasks } from './pages/Tasks'
import { Profiles } from './pages/Profiles'
import { Cards } from './pages/Cards'
import { Settings } from './pages/Settings'
import { useWebSocket } from './hooks/useWebSocket'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 5_000 } },
})

function AppInner() {
  useWebSocket()
  return (
    <div className="min-h-screen bg-background md:flex">
      <Sidebar />
      <main className="flex-1 overflow-x-hidden pb-24 md:pb-0">
        <Routes>
          <Route path="/" element={<Tasks />} />
          <Route path="/profiles" element={<Profiles />} />
          <Route path="/cards" element={<Cards />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider delayDuration={200}>
        <BrowserRouter>
          <AppInner />
        </BrowserRouter>
        <Toaster position="bottom-right" richColors />
      </TooltipProvider>
    </QueryClientProvider>
  )
}
