import { Eraser, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { aiApi } from '../../api/api'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { useAsync } from '../../hooks/useAsync'
import { useMutation } from '../../hooks/useMutation'
import styles from './AIPlaygroundPage.module.css'
import { ChatMessage } from './ChatMessage'
import { Composer } from './Composer'
import { SettingsPanel } from './SettingsPanel'
import { DEFAULT_SETTINGS } from './settings'

const SUGGESTIONS = [
  'Pitch a hackathon project that uses AI and file storage in two sentences.',
  'Explain retrieval-augmented generation to a first-year student.',
  'Return a JSON object with 3 feature ideas for a todo app (use JSON mode).',
]

let messageId = 0
const newId = () => ++messageId

function buildPayload(history, settings) {
  const messages = history.filter((m) => m.role === 'user' || m.role === 'assistant').map(({ role, content }) => ({ role, content }))
  if (settings.system.trim()) messages.unshift({ role: 'system', content: settings.system.trim() })
  return {
    messages,
    provider: settings.provider || undefined,
    model: settings.provider && settings.model.trim() ? settings.model.trim() : undefined,
    temperature: settings.temperature,
    max_tokens: settings.maxTokens ? Number(settings.maxTokens) : undefined,
    json_mode: settings.jsonMode,
  }
}

export default function AIPlaygroundPage() {
  const [messages, setMessages] = useState([])
  const [settings, setSettings] = useState(DEFAULT_SETTINGS)
  const providers = useAsync(({ signal }) => aiApi.providers({ signal }), [])
  const chat = useMutation(aiApi.chat, { errorToast: false }) // errors render inline in the thread
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' })
  }, [messages, chat.loading])

  const send = async (history) => {
    setMessages(history)
    const { data, error } = await chat.mutate(buildPayload(history, settings))
    setMessages((current) => [
      ...current,
      error ? { id: newId(), role: 'error', error } : { id: newId(), role: 'assistant', content: data.text, response: data, jsonMode: settings.jsonMode },
    ])
  }

  const handleSend = (text) => send([...messages.filter((m) => m.role !== 'error'), { id: newId(), role: 'user', content: text }])

  const retry = () => send(messages.filter((m) => m.role !== 'error'))

  return (
    <>
      <PageHeader
        icon={Sparkles}
        title="AI Playground"
        description="Talk to the backend's LLM client. In auto mode it walks the provider chain and falls back on failure; the trail under each reply shows every attempt."
        actions={
          <Button leftIcon={Eraser} onClick={() => setMessages([])} disabled={!messages.length || chat.loading}>
            Clear chat
          </Button>
        }
      />

      <div className={styles.layout}>
        <section className={styles.chat} aria-label="Conversation">
          <div className={styles.thread} aria-live="polite">
            {messages.length === 0 && !chat.loading ? (
              <div className={styles.intro}>
                <span className={styles.introIcon}>
                  <Sparkles size={22} aria-hidden="true" />
                </span>
                <h2>Start a conversation</h2>
                <p>Messages go to POST /ai/chat with the full history. Try one of these:</p>
                <div className={styles.suggestions}>
                  {SUGGESTIONS.map((s) => (
                    <button key={s} type="button" className={styles.suggestion} onClick={() => handleSend(s)}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m, i) => <ChatMessage key={m.id} message={m} onRetry={i === messages.length - 1 ? retry : undefined} />)
            )}
            {chat.loading && <ChatMessage message={{ role: 'assistant', pending: true }} />}
            <div ref={endRef} />
          </div>
          <Composer onSend={handleSend} loading={chat.loading} />
        </section>

        <SettingsPanel settings={settings} onChange={setSettings} providers={providers} />
      </div>
    </>
  )
}
