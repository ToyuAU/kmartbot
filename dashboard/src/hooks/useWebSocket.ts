/**
 * Maintains a single WebSocket connection to the backend.
 * Automatically reconnects on disconnect with exponential backoff.
 * Dispatches incoming events to the Zustand store.
 */

import { useEffect, useRef } from 'react'
import { toast } from 'sonner'
import { useStore } from '../store'
import type { TaskLog } from '../api/client'

const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`

export function useWebSocket() {
  const setWsConnected = useStore((s) => s.setWsConnected)
  const setTaskState = useStore((s) => s.setTaskState)
  const appendLog = useStore((s) => s.appendLog)

  const retryDelay = useRef(1000)
  const ws = useRef<WebSocket | null>(null)
  const unmounted = useRef(false)

  useEffect(() => {
    unmounted.current = false

    function connect() {
      if (unmounted.current) return
      const socket = new WebSocket(WS_URL)
      ws.current = socket

      socket.onopen = () => {
        setWsConnected(true)
        retryDelay.current = 1000
      }

      socket.onclose = () => {
        setWsConnected(false)
        if (!unmounted.current) {
          setTimeout(connect, retryDelay.current)
          retryDelay.current = Math.min(retryDelay.current * 2, 30_000)
        }
      }

      socket.onerror = () => {
        socket.close()
      }

      socket.onmessage = (ev) => {
        try {
          const event = JSON.parse(ev.data)
          handleEvent(event)
        } catch {
          // ignore malformed
        }
      }
    }

    function handleEvent(event: Record<string, unknown>) {
      switch (event.type) {
        case 'task_update': {
          const status = event.status as import('../store').TaskStatus
          const orderNumber = event.order_number as string | undefined
          const errMsg = event.error_message as string | undefined
          setTaskState(event.task_id as string, {
            status,
            step: (event.step as string) ?? '',
            order_number: orderNumber,
            error_message: errMsg,
          })
          if (status === 'success' && orderNumber) {
            toast.success(`Order placed: ${orderNumber}`)
          } else if (status === 'failed' && errMsg) {
            toast.error(`Task failed: ${errMsg}`)
          }
          break
        }
        case 'task_log':
          appendLog({
            id: Date.now(),
            task_id: event.task_id as string,
            level: event.level as TaskLog['level'],
            message: event.message as string,
            step: (event.step as string) ?? '',
            ts: (event.ts as string) ?? new Date().toISOString(),
          })
          break
        case 'ping':
          break
      }
    }

    connect()
    return () => {
      unmounted.current = true
      ws.current?.close()
    }
  }, [])
}
