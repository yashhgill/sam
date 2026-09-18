import React, { useState, useEffect, useRef, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { motion, AnimatePresence } from 'framer-motion'
import { useChatStore } from './stores/chat'
import { useChat } from './hooks/useChat'

// ── Wake word config ───────────────────────────────────────────────────────────
const WAKE_WORDS = ['hey sam', 'ok sam', 'hey s.a.m', 'sam']

// ── Agent colors ───────────────────────────────────────────────────────────────
const AGENT_COLORS: Record<string, string> = {
  conversation: '#6366f1',
  research: '#06b6d4',
  coding: '#10b981',
  computer: '#f59e0b',
  smart_home: '#8b5cf6',
  calendar: '#ec4899',
  communication: '#3b82f6',
  music: '#f43f5e',
  file: '#84cc16',
  automation: '#fb923c',
  memory: '#a78bfa',
}

const AGENT_LABELS: Record<string, string> = {
  conversation: 'SAM',
  research: 'Research',
  coding: 'Code',
  computer: 'Control',
  smart_home: 'Home',
  calendar: 'Calendar',
  communication: 'Comms',
  music: 'Music',
  file: 'Files',
  automation: 'Auto',
  memory: 'Memory',
}

// ── 3D Animated Orb ───────────────────────────────────────────────────────────
function SAMOrb({ isActive, isListening, agentColor }: {
  isActive: boolean
  isListening: boolean
  agentColor: string
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const animRef = useRef<number>()
  const timeRef = useRef(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    const size = 120
    canvas.width = size
    canvas.height = size

    const parseColor = (hex: string) => {
      const r = parseInt(hex.slice(1, 3), 16)
      const g = parseInt(hex.slice(3, 5), 16)
      const b = parseInt(hex.slice(5, 7), 16)
      return { r, g, b }
    }

    const animate = () => {
      timeRef.current += isActive ? 0.04 : 0.015
      const t = timeRef.current
      const cx = size / 2
      const cy = size / 2

      ctx.clearRect(0, 0, size, size)

      const col = parseColor(agentColor)

      // Outer glow rings
      const ringCount = isListening ? 4 : 2
      for (let i = 0; i < ringCount; i++) {
        const phase = t + (i * Math.PI) / ringCount
        const radius = 38 + Math.sin(phase) * (isListening ? 10 : 4) + i * 4
        const alpha = (0.15 - i * 0.03) * (isListening ? 1.5 : 1)
        ctx.beginPath()
        ctx.arc(cx, cy, radius, 0, Math.PI * 2)
        ctx.strokeStyle = `rgba(${col.r},${col.g},${col.b},${alpha})`
        ctx.lineWidth = isListening ? 2 : 1.5
        ctx.stroke()
      }

      // Core sphere gradient
      const baseRadius = 28 + Math.sin(t * 1.5) * (isActive ? 3 : 1)
      const grad = ctx.createRadialGradient(cx - 6, cy - 6, 2, cx, cy, baseRadius)
      grad.addColorStop(0, `rgba(255,255,255,0.9)`)
      grad.addColorStop(0.3, `rgba(${col.r},${col.g},${col.b},0.95)`)
      grad.addColorStop(0.7, `rgba(${Math.floor(col.r * 0.6)},${Math.floor(col.g * 0.6)},${Math.floor(col.b * 0.6)},0.9)`)
      grad.addColorStop(1, `rgba(${Math.floor(col.r * 0.3)},${Math.floor(col.g * 0.3)},${Math.floor(col.b * 0.3)},0.8)`)

      ctx.beginPath()
      ctx.arc(cx, cy, baseRadius, 0, Math.PI * 2)
      ctx.fillStyle = grad
      ctx.fill()

      // Specular highlight
      const specGrad = ctx.createRadialGradient(cx - 8, cy - 9, 0, cx - 8, cy - 9, 12)
      specGrad.addColorStop(0, 'rgba(255,255,255,0.7)')
      specGrad.addColorStop(1, 'rgba(255,255,255,0)')
      ctx.beginPath()
      ctx.arc(cx - 8, cy - 9, 12, 0, Math.PI * 2)
      ctx.fillStyle = specGrad
      ctx.fill()

      // Orbiting particles when active
      if (isActive || isListening) {
        const particleCount = isListening ? 6 : 3
        for (let i = 0; i < particleCount; i++) {
          const angle = t * (isListening ? 2 : 1.2) + (i * Math.PI * 2) / particleCount
          const orbitR = 36 + Math.sin(t + i) * 4
          const px = cx + Math.cos(angle) * orbitR
          const py = cy + Math.sin(angle) * orbitR
          const pSize = 2.5 + Math.sin(t * 2 + i) * 1
          ctx.beginPath()
          ctx.arc(px, py, pSize, 0, Math.PI * 2)
          ctx.fillStyle = `rgba(${col.r},${col.g},${col.b},0.8)`
          ctx.fill()
        }
      }

      animRef.current = requestAnimationFrame(animate)
    }

    animate()
    return () => { if (animRef.current) cancelAnimationFrame(animRef.current) }
  }, [isActive, isListening, agentColor])

  return (
    <div style={{ position: 'relative', width: 120, height: 120, flexShrink: 0 }}>
      <canvas ref={canvasRef} style={{ display: 'block' }} />
      {isListening && (
        <div style={{
          position: 'absolute', inset: 0,
          borderRadius: '50%',
          boxShadow: `0 0 30px 8px ${agentColor}55`,
          animation: 'pulse-ring 1s ease-in-out infinite',
          pointerEvents: 'none',
        }} />
      )}
    </div>
  )
}

// ── Waveform visualizer ────────────────────────────────────────────────────────
function Waveform({ active }: { active: boolean }) {
  const bars = 20
  return (
    <div style={{ display: 'flex', gap: 3, alignItems: 'center', height: 32 }}>
      {Array.from({ length: bars }).map((_, i) => (
        <motion.div
          key={i}
          animate={active ? {
            height: [4, Math.random() * 24 + 4, 4],
          } : { height: 4 }}
          transition={{
            duration: 0.4 + Math.random() * 0.4,
            repeat: Infinity,
            delay: i * 0.05,
            ease: 'easeInOut',
          }}
          style={{
            width: 3,
            background: 'var(--accent)',
            borderRadius: 2,
            opacity: active ? 1 : 0.3,
          }}
        />
      ))}
    </div>
  )
}

// ── Typing dots ────────────────────────────────────────────────────────────────
function TypingDots() {
  return (
    <div style={{ display: 'flex', gap: 5, alignItems: 'center', padding: '4px 0' }}>
      {[0, 1, 2].map(i => (
        <motion.div
          key={i}
          animate={{ y: [0, -6, 0], opacity: [0.4, 1, 0.4] }}
          transition={{ duration: 0.8, delay: i * 0.15, repeat: Infinity }}
          style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)' }}
        />
      ))}
    </div>
  )
}

// ── Code block ────────────────────────────────────────────────────────────────
function CodeBlock({ children, className }: { children?: React.ReactNode; className?: string }) {
  const [copied, setCopied] = useState(false)
  const code = String(children).replace(/\n$/, '')
  const lang = className?.replace('language-', '') || 'code'

  const copy = () => {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div style={{
      background: '#0d0d14', border: '1px solid #2a2a3a',
      borderRadius: 10, overflow: 'hidden', margin: '8px 0',
    }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '6px 14px', background: '#16162a', borderBottom: '1px solid #2a2a3a',
      }}>
        <span style={{ fontSize: 11, color: '#6366f1', fontFamily: 'monospace', fontWeight: 600 }}>{lang}</span>
        <button onClick={copy} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: copied ? '#10b981' : '#666', fontSize: 11, fontFamily: 'monospace',
        }}>
          {copied ? '✓ copied' : 'copy'}
        </button>
      </div>
      <pre style={{ margin: 0, padding: '12px 14px', overflowX: 'auto' }}>
        <code style={{ fontFamily: 'JetBrains Mono, Fira Code, monospace', fontSize: 13, color: '#e2e8f0', lineHeight: 1.6 }}>
          {code}
        </code>
      </pre>
    </div>
  )
}

// ── Message bubble ─────────────────────────────────────────────────────────────
function MessageBubble({ msg, agentColor }: {
  msg: ReturnType<typeof useChatStore.getState>['messages'][0]
  agentColor: string
}) {
  const isUser = msg.role === 'user'
  const [copied, setCopied] = useState(false)

  const copy = () => {
    navigator.clipboard.writeText(msg.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      style={{
        display: 'flex',
        flexDirection: isUser ? 'row-reverse' : 'row',
        gap: 12, alignItems: 'flex-start',
      }}
    >
      {!isUser && (
        <div style={{
          width: 34, height: 34, borderRadius: 10, flexShrink: 0,
          background: `linear-gradient(135deg, ${agentColor}, ${agentColor}88)`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 13, fontWeight: 800, color: '#fff',
          boxShadow: `0 0 12px ${agentColor}44`,
          marginTop: 2,
        }}>
          S
        </div>
      )}

      <div style={{ maxWidth: '78%', minWidth: 0 }}>
        {!isUser && msg.agent && msg.agent !== 'conversation' && (
          <div style={{
            fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
            color: agentColor, marginBottom: 4, textTransform: 'uppercase',
          }}>
            {AGENT_LABELS[msg.agent] || msg.agent}
          </div>
        )}

        <div style={{
          background: isUser
            ? `linear-gradient(135deg, ${agentColor}, ${agentColor}cc)`
            : 'rgba(255,255,255,0.04)',
          border: isUser ? 'none' : '1px solid rgba(255,255,255,0.08)',
          borderRadius: isUser ? '18px 18px 4px 18px' : '4px 18px 18px 18px',
          padding: isUser ? '10px 16px' : '12px 16px',
          backdropFilter: 'blur(10px)',
          boxShadow: isUser ? `0 4px 20px ${agentColor}33` : 'none',
        }}>
          {msg.content === '' && msg.streaming ? (
            <TypingDots />
          ) : isUser ? (
            <p style={{ margin: 0, fontSize: '0.9375rem', lineHeight: 1.65, color: '#fff' }}>
              {msg.content}
            </p>
          ) : (
            <div className="prose">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ className, children, ...props }: any) {
                    const isBlock = className?.startsWith('language-')
                    return isBlock
                      ? <CodeBlock className={className}>{children}</CodeBlock>
                      : <code style={{
                          background: 'rgba(99,102,241,0.2)',
                          borderRadius: 4, padding: '1px 6px',
                          fontFamily: 'monospace', fontSize: '0.875em', color: '#a5b4fc',
                        }} {...props}>{children}</code>
                  }
                }}
              >
                {msg.content}
              </ReactMarkdown>
              {msg.streaming && msg.content && (
                <span className="cursor" />
              )}
            </div>
          )}
        </div>

        {!isUser && !msg.streaming && msg.content && (
          <div style={{ display: 'flex', gap: 8, marginTop: 5, paddingLeft: 2 }}>
            {msg.toolsUsed && msg.toolsUsed.length > 0 && (
              <span style={{ fontSize: 10, color: '#4b5563' }}>
                ⚡ {msg.toolsUsed.join(', ')}
              </span>
            )}
            <button onClick={copy} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: copied ? '#10b981' : '#4b5563', fontSize: 11, padding: 0,
            }}>
              {copied ? '✓ copied' : 'copy'}
            </button>
          </div>
        )}
      </div>
    </motion.div>
  )
}

// ── Wake word indicator ────────────────────────────────────────────────────────
function WakeWordBadge({ active, listening }: { active: boolean; listening: boolean }) {
  return (
    <motion.div
      animate={{ opacity: 1 }}
      style={{
        display: 'flex', alignItems: 'center', gap: 6,
        padding: '4px 10px',
        background: active ? 'rgba(99,102,241,0.15)' : 'rgba(255,255,255,0.04)',
        border: `1px solid ${active ? 'rgba(99,102,241,0.4)' : 'rgba(255,255,255,0.08)'}`,
        borderRadius: 20, fontSize: 11,
        color: active ? '#818cf8' : '#4b5563',
        transition: 'all 0.3s',
      }}
    >
      <motion.div
        animate={{ scale: active ? [1, 1.3, 1] : 1 }}
        transition={{ duration: 1.2, repeat: active ? Infinity : 0 }}
        style={{
          width: 6, height: 6, borderRadius: '50%',
          background: listening ? '#f43f5e' : active ? '#6366f1' : '#374151',
        }}
      />
      {listening ? 'Listening...' : active ? 'Wake word on' : 'Say "Hey SAM"'}
    </motion.div>
  )
}

// ── Quick action chips ─────────────────────────────────────────────────────────
const QUICK_ACTIONS = [
  { label: '🔍 Search the web', prompt: 'Search the web for ' },
  { label: '💻 Write code', prompt: 'Write a ' },
  { label: '📝 Draft a document', prompt: 'Write a professional ' },
  { label: '🧠 Remember this', prompt: 'Remember that ' },
  { label: '🌐 Build a website', prompt: 'Create a complete website for ' },
  { label: '🔧 Debug my code', prompt: 'Debug this code: ' },
]

// ── Main App ───────────────────────────────────────────────────────────────────
export default function App() {
  const store = useChatStore()
  const { sendMessage, stop } = useChat()
  const [input, setInput] = useState('')
  const [isListening, setIsListening] = useState(false)
  const [wakeWordActive, setWakeWordActive] = useState(false)
  const [showSidebar, setShowSidebar] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const recognitionRef = useRef<any>(null)
  const wakeRecognitionRef = useRef<any>(null)
  const wakeWordEnabledRef = useRef(false)

  const agentColor = AGENT_COLORS[store.currentAgent] || '#6366f1'

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [store.messages, store.isStreaming])

  // Focus on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Start voice input for message
  const startVoice = useCallback((onResult: (text: string) => void, onEnd: () => void) => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SR) return
    const rec = new SR()
    rec.lang = 'en-US'
    rec.continuous = false
    rec.interimResults = true
    rec.onresult = (e: any) => {
      const transcript = Array.from(e.results).map((r: any) => r[0].transcript).join('')
      onResult(transcript)
    }
    rec.onend = onEnd
    rec.onerror = onEnd
    rec.start()
    return rec
  }, [])

  // Toggle manual voice input
  const toggleVoice = () => {
    if (isListening) {
      recognitionRef.current?.stop()
      setIsListening(false)
      return
    }
    setIsListening(true)
    recognitionRef.current = startVoice(
      (text) => setInput(text),
      () => setIsListening(false),
    )
  }

  // Wake word detection — always listening in background
  const startWakeWord = useCallback(() => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SR || !wakeWordEnabledRef.current) return

    const rec = new SR()
    rec.lang = 'en-US'
    rec.continuous = true
    rec.interimResults = true

    rec.onresult = (e: any) => {
      const transcript = Array.from(e.results)
        .map((r: any) => r[0].transcript.toLowerCase().trim())
        .join(' ')

      const triggered = WAKE_WORDS.some(w => transcript.includes(w))
      if (triggered) {
        rec.stop()
        // Strip wake word from transcript to get actual query
        let query = transcript
        for (const w of WAKE_WORDS) {
          query = query.replace(w, '').trim()
        }

        if (query.length > 2) {
          // Has a command after wake word — send directly
          sendMessage(query)
        } else {
          // Just wake word — start listening for command
          setIsListening(true)
          recognitionRef.current = startVoice(
            (text) => setInput(text),
            () => {
              setIsListening(false)
              // Auto-send if there's content
              setTimeout(() => {
                const inp = inputRef.current?.value.trim()
                if (inp) {
                  sendMessage(inp)
                  setInput('')
                }
              }, 300)
            },
          )
        }
      }
    }

    rec.onend = () => {
      if (wakeWordEnabledRef.current) {
        setTimeout(startWakeWord, 500) // restart
      }
    }
    rec.onerror = () => {
      if (wakeWordEnabledRef.current) {
        setTimeout(startWakeWord, 1000)
      }
    }

    rec.start()
    wakeRecognitionRef.current = rec
  }, [sendMessage, startVoice])

  const toggleWakeWord = () => {
    if (wakeWordActive) {
      wakeWordEnabledRef.current = false
      wakeRecognitionRef.current?.stop()
      setWakeWordActive(false)
    } else {
      wakeWordEnabledRef.current = true
      setWakeWordActive(true)
      startWakeWord()
    }
  }

  const handleSend = () => {
    const text = input.trim()
    if (!text || store.isStreaming) return
    setInput('')
    sendMessage(text)
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleQuickAction = (prompt: string) => {
    setInput(prompt)
    inputRef.current?.focus()
  }

  const agentLabel = AGENT_LABELS[store.currentAgent] || store.currentAgent
  const isEmpty = store.messages.length === 0

  return (
    <div style={{
      display: 'flex', height: '100vh',
      background: 'var(--bg)', overflow: 'hidden',
      fontFamily: 'Inter, -apple-system, sans-serif',
    }}>
      {/* ── Sidebar ── */}
      <AnimatePresence>
        {showSidebar && (
          <motion.div
            initial={{ x: -280, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: -280, opacity: 0 }}
            transition={{ type: 'spring', damping: 28, stiffness: 300 }}
            style={{
              width: 260, background: 'rgba(10,10,20,0.95)',
              borderRight: '1px solid rgba(255,255,255,0.06)',
              backdropFilter: 'blur(20px)',
              display: 'flex', flexDirection: 'column',
              padding: '20px 16px', gap: 24, flexShrink: 0,
            }}
          >
            <div style={{ fontWeight: 800, fontSize: 18, color: '#fff', letterSpacing: '-0.02em' }}>
              SAM
              <span style={{ color: '#6366f1' }}> Ultra</span>
            </div>

            {/* Quick actions */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, color: '#4b5563', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 10 }}>
                Quick Actions
              </div>
              {QUICK_ACTIONS.map(a => (
                <button
                  key={a.label}
                  onClick={() => { handleQuickAction(a.prompt); setShowSidebar(false) }}
                  style={{
                    width: '100%', background: 'transparent', border: 'none',
                    cursor: 'pointer', color: '#9ca3af', fontSize: 13,
                    padding: '8px 10px', borderRadius: 8, textAlign: 'left',
                    display: 'block', marginBottom: 2,
                    transition: 'all 0.15s',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'rgba(99,102,241,0.1)', e.currentTarget.style.color = '#c7d2fe')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent', e.currentTarget.style.color = '#9ca3af')}
                >
                  {a.label}
                </button>
              ))}
            </div>

            {/* Agents */}
            <div>
              <div style={{ fontSize: 10, fontWeight: 700, color: '#4b5563', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 10 }}>
                Agents
              </div>
              {Object.entries(AGENT_LABELS).map(([key, label]) => (
                <div key={key} style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '6px 10px', borderRadius: 8,
                  background: store.currentAgent === key ? 'rgba(99,102,241,0.1)' : 'transparent',
                  marginBottom: 2,
                }}>
                  <div style={{
                    width: 8, height: 8, borderRadius: '50%',
                    background: AGENT_COLORS[key] || '#6366f1',
                  }} />
                  <span style={{ fontSize: 13, color: store.currentAgent === key ? '#c7d2fe' : '#6b7280' }}>
                    {label}
                  </span>
                </div>
              ))}
            </div>

            {/* Wake word toggle */}
            <div style={{ marginTop: 'auto' }}>
              <button
                onClick={() => { toggleWakeWord(); setShowSidebar(false) }}
                style={{
                  width: '100%', padding: '10px 14px', borderRadius: 10,
                  border: `1px solid ${wakeWordActive ? 'rgba(99,102,241,0.4)' : 'rgba(255,255,255,0.08)'}`,
                  background: wakeWordActive ? 'rgba(99,102,241,0.1)' : 'transparent',
                  color: wakeWordActive ? '#818cf8' : '#6b7280',
                  cursor: 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8,
                }}
              >
                <span>{wakeWordActive ? '🟣' : '⚫'}</span>
                {wakeWordActive ? 'Wake word ON' : 'Enable "Hey SAM"'}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Main content ── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>

        {/* ── Header ── */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 20px', height: 58,
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          background: 'rgba(10,10,20,0.8)',
          backdropFilter: 'blur(20px)',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button
              onClick={() => setShowSidebar(v => !v)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: '#6b7280', fontSize: 20, lineHeight: 1, padding: '4px 6px',
              }}
            >
              ☰
            </button>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <motion.div
                animate={{ scale: store.isStreaming ? [1, 1.1, 1] : 1 }}
                transition={{ duration: 1.5, repeat: store.isStreaming ? Infinity : 0 }}
                style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: store.isStreaming ? '#f59e0b' : '#10b981',
                  boxShadow: `0 0 6px ${store.isStreaming ? '#f59e0b' : '#10b981'}`,
                }}
              />
              <span style={{ fontWeight: 700, fontSize: 15, color: '#fff' }}>SAM</span>
              <span style={{
                fontSize: 11, color: agentColor, fontWeight: 600,
                padding: '2px 8px', borderRadius: 20,
                background: `${agentColor}22`,
                border: `1px solid ${agentColor}44`,
              }}>
                {agentLabel}
              </span>
            </div>

            {store.currentModel && (
              <span style={{ fontSize: 11, color: '#374151' }}>
                {store.currentModel.split('/').pop()?.split('-').slice(0, 3).join('-')}
              </span>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <AnimatePresence>
              {store.activeTool && (
                <motion.span
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.8 }}
                  style={{
                    fontSize: 11, padding: '3px 10px', borderRadius: 20,
                    background: 'rgba(251,191,36,0.1)',
                    border: '1px solid rgba(251,191,36,0.3)',
                    color: '#fbbf24',
                  }}
                >
                  ⚡ {store.activeTool}
                </motion.span>
              )}
              {store.emotion && store.emotion.mood !== 'neutral' && (
                <motion.span
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  style={{
                    fontSize: 11, padding: '3px 10px', borderRadius: 20,
                    background: 'rgba(99,102,241,0.1)',
                    border: '1px solid rgba(99,102,241,0.3)',
                    color: '#818cf8',
                  }}
                >
                  {store.emotion.mood}
                </motion.span>
              )}
            </AnimatePresence>

            <WakeWordBadge active={wakeWordActive} listening={isListening} />

            <button
              onClick={store.clearMessages}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: '#4b5563', fontSize: 18, padding: '4px 6px',
              }}
              title="Clear chat"
            >
              ✕
            </button>
          </div>
        </div>

        {/* ── Messages area ── */}
        <div style={{
          flex: 1, overflowY: 'auto', padding: '24px 20px',
          display: 'flex', flexDirection: 'column', gap: 20,
        }}>
          {/* Empty state with 3D orb */}
          {isEmpty && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center',
                justifyContent: 'center', height: '100%', gap: 24,
              }}
            >
              <SAMOrb isActive={store.isStreaming} isListening={isListening} agentColor={agentColor} />

              <div style={{ textAlign: 'center' }}>
                <div style={{
                  fontSize: 28, fontWeight: 800, color: '#fff',
                  letterSpacing: '-0.03em', marginBottom: 8,
                }}>
                  Hello, I'm <span style={{ color: agentColor }}>SAM</span>
                </div>
                <div style={{ fontSize: 15, color: '#6b7280', lineHeight: 1.6 }}>
                  Your personal AI — coding, research, writing, web, everything.<br/>
                  Say <span style={{ color: '#818cf8' }}>"Hey SAM"</span> or type below.
                </div>
              </div>

              {/* Capability pills */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', maxWidth: 500 }}>
                {[
                  '🌐 Build websites', '💻 Write & debug code', '🔍 Web research',
                  '📝 Draft documents', '🧠 Long-term memory', '🗂 File management',
                  '⚡ Automations', '🎙 Voice control',
                ].map(cap => (
                  <div key={cap} style={{
                    fontSize: 12, padding: '5px 12px', borderRadius: 20,
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    color: '#9ca3af',
                  }}>
                    {cap}
                  </div>
                ))}
              </div>

              {/* Quick prompts */}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center', maxWidth: 480 }}>
                {[
                  'Build me a landing page for my startup',
                  'Write a Python web scraper',
                  'Research the latest AI news',
                  'Draft a professional email',
                ].map(q => (
                  <button
                    key={q}
                    onClick={() => { setInput(q); setTimeout(handleSend, 0) }}
                    style={{
                      background: 'rgba(99,102,241,0.08)',
                      border: '1px solid rgba(99,102,241,0.2)',
                      borderRadius: 10, padding: '8px 14px',
                      color: '#818cf8', fontSize: 13, cursor: 'pointer',
                      transition: 'all 0.15s',
                    }}
                    onMouseEnter={e => {
                      e.currentTarget.style.background = 'rgba(99,102,241,0.15)'
                      e.currentTarget.style.borderColor = 'rgba(99,102,241,0.4)'
                    }}
                    onMouseLeave={e => {
                      e.currentTarget.style.background = 'rgba(99,102,241,0.08)'
                      e.currentTarget.style.borderColor = 'rgba(99,102,241,0.2)'
                    }}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </motion.div>
          )}

          {/* Messages */}
          {store.messages.map(msg => (
            <MessageBubble key={msg.id} msg={msg} agentColor={agentColor} />
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* ── Input area ── */}
        <div style={{
          padding: '12px 20px 20px',
          borderTop: '1px solid rgba(255,255,255,0.06)',
          background: 'rgba(10,10,20,0.8)',
          backdropFilter: 'blur(20px)',
          flexShrink: 0,
        }}>
          {/* Listening waveform */}
          <AnimatePresence>
            {isListening && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 44 }}
                exit={{ opacity: 0, height: 0 }}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  marginBottom: 10,
                }}
              >
                <Waveform active={isListening} />
                <span style={{ fontSize: 12, color: '#818cf8', marginLeft: 12 }}>
                  Listening...
                </span>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Input box */}
          <div style={{
            display: 'flex', gap: 10, alignItems: 'flex-end',
            background: 'rgba(255,255,255,0.04)',
            border: `1px solid ${store.isStreaming ? `${agentColor}66` : 'rgba(255,255,255,0.1)'}`,
            borderRadius: 16, padding: '10px 10px 10px 16px',
            transition: 'border-color 0.2s',
            boxShadow: store.isStreaming ? `0 0 20px ${agentColor}22` : 'none',
          }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder={isListening ? 'Speak now...' : 'Message SAM... (or say "Hey SAM")'}
              rows={1}
              style={{
                flex: 1, background: 'none', border: 'none', outline: 'none',
                color: '#e2e8f0', fontSize: '0.9375rem', resize: 'none',
                fontFamily: 'Inter, sans-serif', lineHeight: 1.6,
                maxHeight: 160, overflowY: 'auto',
              }}
              onInput={e => {
                const t = e.target as HTMLTextAreaElement
                t.style.height = 'auto'
                t.style.height = Math.min(t.scrollHeight, 160) + 'px'
              }}
            />

            {/* Voice button */}
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={toggleVoice}
              style={{
                width: 38, height: 38, borderRadius: 10, border: 'none',
                cursor: 'pointer', flexShrink: 0, display: 'flex',
                alignItems: 'center', justifyContent: 'center', fontSize: 18,
                background: isListening ? 'rgba(244,63,94,0.15)' : 'rgba(255,255,255,0.06)',
                color: isListening ? '#f43f5e' : '#6b7280',
                transition: 'all 0.15s',
              }}
              title={isListening ? 'Stop' : 'Voice input'}
            >
              🎙
            </motion.button>

            {/* Wake word toggle */}
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={toggleWakeWord}
              style={{
                width: 38, height: 38, borderRadius: 10, border: 'none',
                cursor: 'pointer', flexShrink: 0, display: 'flex',
                alignItems: 'center', justifyContent: 'center', fontSize: 16,
                background: wakeWordActive ? 'rgba(99,102,241,0.15)' : 'rgba(255,255,255,0.06)',
                color: wakeWordActive ? '#818cf8' : '#6b7280',
                transition: 'all 0.15s',
              }}
              title={wakeWordActive ? 'Disable wake word' : 'Enable "Hey SAM" wake word'}
            >
              {wakeWordActive ? '👂' : '🔇'}
            </motion.button>

            {/* Send / Stop */}
            {store.isStreaming ? (
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={stop}
                style={{
                  width: 38, height: 38, borderRadius: 10, border: 'none',
                  cursor: 'pointer', background: 'rgba(244,63,94,0.15)',
                  color: '#f43f5e', flexShrink: 0, fontSize: 16,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}
              >
                ⏹
              </motion.button>
            ) : (
              <motion.button
                whileHover={{ scale: input.trim() ? 1.05 : 1 }}
                whileTap={{ scale: input.trim() ? 0.95 : 1 }}
                onClick={handleSend}
                disabled={!input.trim()}
                style={{
                  width: 38, height: 38, borderRadius: 10, border: 'none',
                  cursor: input.trim() ? 'pointer' : 'not-allowed',
                  background: input.trim() ? agentColor : 'rgba(255,255,255,0.06)',
                  color: input.trim() ? '#fff' : '#4b5563',
                  flexShrink: 0, fontSize: 16,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  boxShadow: input.trim() ? `0 0 16px ${agentColor}66` : 'none',
                  transition: 'all 0.15s',
                }}
              >
                ↑
              </motion.button>
            )}
          </div>

          <div style={{
            fontSize: 11, color: '#374151', textAlign: 'center', marginTop: 8,
          }}>
            Enter to send · Shift+Enter for newline · Say "Hey SAM" to activate hands-free
          </div>
        </div>
      </div>
    </div>
  )
}
