import { useCallback, useRef } from 'react'
import { useChatStore } from '../stores/chat'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export function useChat() {
  const store = useChatStore()
  const abortRef = useRef<AbortController | null>(null)

  const sendMessage = useCallback(async (text: string, device = 'web') => {
    if (store.isStreaming) {
      abortRef.current?.abort()
    }

    // Add user message
    store.addMessage({ role: 'user', content: text })

    // Add placeholder for assistant
    const assistantId = store.addMessage({
      role: 'assistant',
      content: '',
      streaming: true,
    })

    store.setStreaming(true)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      const resp = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          session_id: store.sessionId,
          device,
          stream: true,
          emotion_detection: true,
        }),
        signal: ctrl.signal,
      })

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`)
      }

      const reader = resp.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      const toolsUsed: string[] = []

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (!raw || raw === '[DONE]') continue

          try {
            const event = JSON.parse(raw)
            handleEvent(event, assistantId, toolsUsed, store)
          } catch {
            // ignore parse errors
          }
        }
      }

      // Finalize
      store.updateMessage(assistantId, {
        streaming: false,
        toolsUsed,
        agent: store.currentAgent,
        model: store.currentModel,
      })

    } catch (err: any) {
      if (err.name === 'AbortError') {
        store.updateMessage(assistantId, { streaming: false, content: store.messages.find(m => m.id === assistantId)?.content || '' })
      } else {
        store.updateMessage(assistantId, {
          streaming: false,
          content: `Error: ${err.message}`,
        })
      }
    } finally {
      store.setStreaming(false)
      store.setActiveTool(null)
    }
  }, [store])

  const stop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  return { sendMessage, stop }
}

function handleEvent(
  event: any,
  assistantId: string,
  toolsUsed: string[],
  store: ReturnType<typeof useChatStore.getState>
) {
  const { type, data } = event

  switch (type) {
    case 'token':
      store.appendToken(assistantId, data)
      break

    case 'session':
      store.setSessionId(data.session_id)
      store.setAgent(data.agent)
      break

    case 'agent_switch':
      store.setAgent(data.agent)
      break

    case 'model':
      store.setModel(data.model)
      break

    case 'emotion':
      store.setEmotion({ mood: data.mood, confidence: data.confidence })
      // Auto-clear after 4s
      setTimeout(() => store.setEmotion(null), 4000)
      break

    case 'tool_start':
      store.setActiveTool(data.name)
      break

    case 'tool_end':
      toolsUsed.push(data.name)
      store.setActiveTool(null)
      break

    case 'error':
      store.updateMessage(assistantId, {
        content: store.messages.find(m => m.id === assistantId)?.content
          ? store.messages.find(m => m.id === assistantId)!.content
          : `Error: ${data?.error || 'Unknown error'}`,
        streaming: false,
      })
      break

    case 'done':
      store.updateMessage(assistantId, { streaming: false })
      break
  }
}
