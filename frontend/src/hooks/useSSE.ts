import { useEffect, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'

export interface SSEEvent {
  type: string
  payload: Record<string, unknown>
  timestamp: string
}

export function useSSE(experimentId: string | undefined, onEvent?: (event: SSEEvent) => void) {
  const queryClient = useQueryClient()
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    if (!experimentId) return

    const source = new EventSource('/api/v1/events/stream')

    source.onmessage = (e) => {
      try {
        const event: SSEEvent = JSON.parse(e.data)
        if (event.payload?.experiment_id !== experimentId) return

        queryClient.invalidateQueries({ queryKey: ['experiment', experimentId] })
        onEventRef.current?.(event)
      } catch {
        // ignore non-JSON keepalive messages
      }
    }

    return () => source.close()
  }, [experimentId, queryClient])
}
