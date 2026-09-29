import { aiApi, API_BASE_URL, healthApi } from '../../api/api'
import { Button, Card, Spinner } from '../../components/ui'
import { useAsync } from '../../hooks'
import styles from './HomePage.module.css'

/** Starter page: shows that the frontend can reach the backend. Replace freely. */
export default function HomePage() {
  const health = useAsync(({ signal }) => healthApi.check({ signal }))
  const ai = useAsync(({ signal }) => aiApi.providers({ signal }))

  return (
    <div className={styles.page}>
      <div>
        <h1 className={styles.title}>Hackathon App</h1>
        <p className={styles.subtitle}>
          Frontend is running. Backend: <code>{API_BASE_URL}</code>
        </p>
      </div>

      <Card
        title="Backend status"
        actions={
          <Button onClick={() => { health.refetch(); ai.refetch() }} loading={health.loading}>
            Refresh
          </Button>
        }
      >
        {health.loading && !health.data ? (
          <Spinner />
        ) : health.error ? (
          <p className={styles.error}>{health.error.message}</p>
        ) : (
          <dl className={styles.list}>
            <dt>API</dt>
            <dd className={styles.ok}>{health.data.status}</dd>
            <dt>Database</dt>
            <dd className={health.data.database === 'ok' ? styles.ok : styles.error}>{health.data.database}</dd>
            <dt>Environment</dt>
            <dd>{health.data.env}</dd>
            <dt>AI providers</dt>
            <dd>
              {ai.data
                ? ai.data.providers.map((p) => `${p.name}${p.configured ? ' ✓' : ''}`).join(' · ')
                : ai.error?.message ?? '…'}
            </dd>
          </dl>
        )}
      </Card>
    </div>
  )
}
