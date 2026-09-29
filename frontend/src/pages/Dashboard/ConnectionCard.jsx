import { KeyRound, Server } from 'lucide-react'
import { useState } from 'react'
import { API_BASE_URL } from '../../api/api'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Input } from '../../components/ui/Input'
import { useAuth } from '../../hooks/useAuth'
import { useToast } from '../../hooks/useToast'
import styles from './ConnectionCard.module.css'

/** Shows where the app points and demos the auth plumbing (token -> Authorization header). */
export function ConnectionCard({ health }) {
  const { token, isAuthenticated, login, logout } = useAuth()
  const { toast } = useToast()
  const [draft, setDraft] = useState('')

  const save = (event) => {
    event.preventDefault()
    if (!draft.trim()) return
    login(draft.trim())
    setDraft('')
    toast.success('Token saved', { description: 'Sent as a Bearer token on every request.' })
  }

  return (
    <Card icon={Server} title="Connection" description="Configured with VITE_API_BASE_URL.">
      <dl className={styles.list}>
        <div>
          <dt>Base URL</dt>
          <dd className="mono">{API_BASE_URL}</dd>
        </div>
        <div>
          <dt>App</dt>
          <dd>{health?.app ?? '—'}</dd>
        </div>
        <div>
          <dt>Environment</dt>
          <dd>{health ? <Badge variant={health.env === 'production' ? 'warning' : 'info'}>{health.env}</Badge> : '—'}</dd>
        </div>
        <div>
          <dt>Latency</dt>
          <dd>{health ? `${health.latencyMs} ms` : '—'}</dd>
        </div>
      </dl>

      <div className={styles.auth}>
        <div className={styles.authHead}>
          <span className={styles.authTitle}>
            <KeyRound size={14} aria-hidden="true" /> Auth token
          </span>
          <Badge variant={isAuthenticated ? 'success' : 'neutral'} dot>
            {isAuthenticated ? 'Attached' : 'None'}
          </Badge>
        </div>
        {isAuthenticated ? (
          <div className={styles.tokenRow}>
            <code className={styles.token}>{`${token.slice(0, 12)}${token.length > 12 ? '…' : ''}`}</code>
            <Button size="sm" variant="secondary" onClick={logout}>
              Clear
            </Button>
          </div>
        ) : (
          <form onSubmit={save} className={styles.tokenRow}>
            <Input aria-label="Bearer token" placeholder="Paste a JWT to test the plumbing" value={draft} onChange={(e) => setDraft(e.target.value)} className={styles.tokenInput} />
            <Button size="md" type="submit" disabled={!draft.trim()}>
              Save
            </Button>
          </form>
        )}
        <p className={styles.hint}>The backend has no auth yet; a 401 response clears the token automatically.</p>
      </div>
    </Card>
  )
}
