import { SendHorizontal } from 'lucide-react'
import { useRef, useState } from 'react'
import { Button } from '../../components/ui/Button'
import styles from './Composer.module.css'

/** Message box: Enter sends, Shift+Enter adds a new line. */
export function Composer({ onSend, loading }) {
  const [text, setText] = useState('')
  const ref = useRef(null)

  const submit = (event) => {
    event?.preventDefault()
    const value = text.trim()
    if (!value || loading) return
    onSend(value)
    setText('')
    ref.current?.focus()
  }

  const onKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) submit(event)
  }

  return (
    <form className={styles.composer} onSubmit={submit}>
      <textarea
        ref={ref}
        className={styles.input}
        rows={1}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask anything…"
        aria-label="Message"
      />
      <Button type="submit" variant="primary" iconOnly leftIcon={SendHorizontal} loading={loading} disabled={!text.trim()} aria-label="Send message" />
      <p className={styles.hint}>
        <kbd>Enter</kbd> to send · <kbd>Shift</kbd> + <kbd>Enter</kbd> for a new line
      </p>
    </form>
  )
}
