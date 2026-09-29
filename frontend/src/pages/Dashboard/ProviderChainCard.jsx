import { ArrowRight, Bot, CircleCheck, CircleMinus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Badge } from '../../components/ui/Badge'
import { Card } from '../../components/ui/Card'
import { ErrorState } from '../../components/ui/ErrorState'
import { Skeleton } from '../../components/ui/Skeleton'
import { cn } from '../../utils/cn'
import styles from './ProviderChainCard.module.css'

export function ProviderChainCard({ data, error, loading, onRetry }) {
  const byName = Object.fromEntries((data?.providers ?? []).map((p) => [p.name, p]))
  const ordered = data ? [...data.provider_order.map((n) => byName[n]).filter(Boolean), ...data.providers.filter((p) => !data.provider_order.includes(p.name))] : []

  return (
    <Card
      icon={Bot}
      title="AI provider chain"
      description={data ? (data.fallback_enabled ? 'Tried in order until one succeeds.' : 'Fallback disabled: only the first provider is used.') : 'Order the backend tries providers in.'}
      actions={data && <Badge variant={data.fallback_enabled ? 'accent' : 'neutral'}>{data.fallback_enabled ? 'Fallback on' : 'Fallback off'}</Badge>}
    >
      {error && <ErrorState error={error} onRetry={onRetry} compact />}
      {loading && !data && (
        <div className={styles.list}>
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} height={52} radius="var(--radius-md)" />
          ))}
        </div>
      )}
      {data && (
        <>
          <ol className={styles.list}>
            {ordered.map((p) => {
              const index = data.active_chain.indexOf(p.name)
              const active = index !== -1
              return (
                <li key={p.name} className={cn(styles.provider, !p.configured && styles.muted)}>
                  <span className={styles.order}>{active ? index + 1 : '–'}</span>
                  <div className={styles.info}>
                    <span className={styles.name}>{p.name}</span>
                    <span className={styles.model}>{p.default_model || 'no default model'}</span>
                  </div>
                  {p.configured ? (
                    <Badge variant="success" icon={CircleCheck}>
                      Configured
                    </Badge>
                  ) : (
                    <Badge variant="neutral" icon={CircleMinus}>
                      No API key
                    </Badge>
                  )}
                </li>
              )
            })}
          </ol>
          <div className={styles.footer}>
            {!data.providers.some((p) => p.configured) ? (
              <p className={styles.hint}>
                Add a key such as <code>GROQ_API_KEY</code> to <code>backend/.env</code> to enable AI features.
              </p>
            ) : (
              <p className={styles.hint}>
                Active chain: <strong>{data.active_chain.join(' → ')}</strong>
              </p>
            )}
            <Link to="/ai" className={styles.cta}>
              Open playground <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </div>
        </>
      )}
    </Card>
  )
}
