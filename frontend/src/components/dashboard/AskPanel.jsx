import { useEffect, useState } from 'react'
import { explainApi } from '../../api/api'
import { simTime } from '../../utils/format'
import { Button, Spinner } from '../ui'
import styles from './Dashboard.module.css'

function errorText(err) {
  if (err.code === 'RATE_LIMITED') return `Too many questions. Try again in ${err.retryAfter ?? 60} s.`
  if (err.code === 'AI_PROVIDERS_FAILED') return 'The AI is not answering right now. Try again in a moment.'
  return err.message
}

/** "Ask AI" about one recommendation: suggested questions, free text, and earlier answers. */
export function AskPanel({ rec }) {
  const [data, setData] = useState(null)
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    const controller = new AbortController()
    explainApi.questions(rec.id, { signal: controller.signal })
      .then(setData)
      .catch((err) => err.name !== 'AbortError' && setError(errorText(err)))
    return () => controller.abort()
  }, [rec.id, rec.status])

  const ask = async (text) => {
    const q = text.trim()
    if (!q || asking) return
    setAsking(true)
    setError(null)
    try {
      const answer = await explainApi.ask(rec.id, q)
      setData((d) => ({ ...d, items: [answer, ...(d?.items ?? [])] }))
      setQuestion('')
    } catch (err) {
      setError(errorText(err))
    } finally {
      setAsking(false)
    }
  }

  return (
    <section className={styles.ask} aria-label={`Ask AI about recommendation ${rec.id}`}>
      {data?.suggestions?.length > 0 && (
        <div className={styles.chips}>
          {data.suggestions.map((s) => (
            <button key={s} type="button" className={styles.chip} disabled={asking} onClick={() => ask(s)}>{s}</button>
          ))}
        </div>
      )}
      <form className={styles.askForm} onSubmit={(e) => { e.preventDefault(); ask(question) }}>
        <input type="text" value={question} maxLength={2000} placeholder="Ask about this decision…"
               aria-label="Question" onChange={(e) => setQuestion(e.target.value)} />
        <Button type="submit" variant="primary" loading={asking} disabled={!question.trim()}>Ask</Button>
      </form>
      {asking && <p className={styles.muted}><Spinner size={14} label="Thinking" /> Reading the latest data and asking the AI…</p>}
      {error && <p className={styles.error} role="alert">{error}</p>}
      {data === null && !error && <Spinner size={14} label="Loading questions" />}
      {data?.items?.map((qa) => (
        <article key={qa.id} className={styles.qa}>
          <p className={styles.question}>{qa.question}</p>
          <p className={styles.answer}>{qa.answer}</p>
          <p className={styles.muted}>
            {qa.model} · tick {qa.tick ?? '–'} · {simTime(qa.created_at)}
            {qa.errors.length > 0 && ` · missing: ${qa.errors.map((e) => e.metric).join(', ')}`}
          </p>
          <details className={styles.explanation}>
            <summary>Data the AI used</summary>
            <pre className={styles.contextJson}>{JSON.stringify(qa.context, null, 2)}</pre>
          </details>
        </article>
      ))}
    </section>
  )
}
