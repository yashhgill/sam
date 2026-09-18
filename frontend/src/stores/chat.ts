import { create } from 'zustand'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  agent?: string
  model?: string
  toolsUsed?: string[]
  timestamp: number
  streaming?: boolean
}

export interface EmotionState {
  mood: string
  confidence: number
}

interface ChatState {
  messages: Message[]
  sessionId: string | null
  isStreaming: boolean
  currentAgent: string
  currentModel: string
  emotion: EmotionState | null
  activeTool: string | null
  wsConnected: boolean

  addMessage: (msg: Omit<Message, 'id' | 'timestamp'>) => string
  updateMessage: (id: string, updates: Partial<Message>) => void
  appendToken: (id: string, token: string) => void
  setAgent: (agent: string) => void
  setModel: (model: string) => void
  setEmotion: (emotion: EmotionState | null) => void
  setActiveTool: (tool: string | null) => void
  setStreaming: (v: boolean) => void
  setSessionId: (id: string) => void
  setWsConnected: (v: boolean) => void
  clearMessages: () => void
}

let _idCounter = 0
const genId = () => `msg_${Date.now()}_${_idCounter++}`

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  sessionId: null,
  isStreaming: false,
  currentAgent: 'conversation',
  currentModel: '',
  emotion: null,
  activeTool: null,
  wsConnected: false,

  addMessage: (msg) => {
    const id = genId()
    set(state => ({
      messages: [...state.messages, { ...msg, id, timestamp: Date.now() }]
    }))
    return id
  },

  updateMessage: (id, updates) => {
    set(state => ({
      messages: state.messages.map(m => m.id === id ? { ...m, ...updates } : m)
    }))
  },

  appendToken: (id, token) => {
    set(state => ({
      messages: state.messages.map(m =>
        m.id === id ? { ...m, content: m.content + token } : m
      )
    }))
  },

  setAgent: (agent) => set({ currentAgent: agent }),
  setModel: (model) => set({ currentModel: model }),
  setEmotion: (emotion) => set({ emotion }),
  setActiveTool: (tool) => set({ activeTool: tool }),
  setStreaming: (v) => set({ isStreaming: v }),
  setSessionId: (id) => set({ sessionId: id }),
  setWsConnected: (v) => set({ wsConnected: v }),
  clearMessages: () => set({ messages: [] }),
}))
