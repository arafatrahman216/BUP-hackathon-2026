import { Activity, ArrowRight, Bot, Database, LayoutDashboard, Package, RefreshCw } from 'lucide-react'
import { useCallback } from 'react'
import { Link } from 'react-router-dom'
import { aiApi, healthApi, itemsApi } from '../../api/api'
import { NAV_ITEMS } from '../../components/layout/navigation'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { ErrorState } from '../../components/ui/ErrorState'
import { useAsync } from '../../hooks/useAsync'
import { formatNumber } from '../../utils/format'
import { ConnectionCard } from './ConnectionCard'
import styles from './DashboardPage.module.css'
import { ProviderChainCard } from './ProviderChainCard'
import { StatCard } from './StatCard'

async function timedHealthCheck({ signal }) {
  const started = performance.now()
  const data = await healthApi.check({ signal, timeout: 10_000 })
  return { ...data, latencyMs: Math.round(performance.now() - started) }
}

export default function DashboardPage() {
  const health = useAsync(timedHealthCheck, [])
  const providers = useAsync(({ signal }) => aiApi.providers({ signal }), [])
  const itemsCount = useAsync(({ signal }) => itemsApi.list({ page: 1, page_size: 1 }, { signal }), [])

  const refreshAll = useCallback(() => {
    health.refetch()
    providers.refetch()
    itemsCount.refetch()
  }, [health, providers, itemsCount])

  const refreshing = health.loading || providers.loading || itemsCount.loading
  const apiDown = health.error?.isNetworkError || health.error?.isTimeout

  const configured = providers.data?.providers.filter((p) => p.configured).length ?? 0
  const totalProviders = providers.data?.providers.length ?? 0

  return (
    <>
      <PageHeader
        icon={LayoutDashboard}
        title="Dashboard"
        description="A live view of the FastAPI backend this template ships with: health, database, the AI provider chain and your data."
        actions={
          <Button leftIcon={RefreshCw} onClick={refreshAll} loading={refreshing}>
            Refresh
          </Button>
        }
      />

      {apiDown && <ErrorState error={health.error} onRetry={refreshAll} retrying={refreshing} className={styles.banner} />}

      <div className={styles.stats}>
        <StatCard
          icon={Activity}
          label="API"
          loading={health.loading && !health.data}
          tone={health.error ? 'danger' : 'success'}
          value={health.error ? 'Offline' : 'Online'}
          meta={health.data ? `${health.data.env} · ${health.data.latencyMs} ms` : health.error?.code}
        />
        <StatCard
          icon={Database}
          label="Database"
          loading={health.loading && !health.data}
          tone={!health.data ? 'neutral' : health.data.database === 'ok' ? 'success' : 'warning'}
          value={!health.data ? 'Unknown' : health.data.database === 'ok' ? 'Connected' : 'Unavailable'}
          meta={health.data ? 'SELECT 1 via /health' : 'Waiting for API'}
        />
        <StatCard
          icon={Bot}
          label="AI providers"
          loading={providers.loading && !providers.data}
          tone={providers.error ? 'danger' : configured > 0 ? 'success' : 'warning'}
          value={providers.data ? `${configured} / ${totalProviders}` : '—'}
          meta={providers.data ? (configured ? 'configured with keys' : 'no API keys yet') : providers.error?.code}
        />
        <StatCard
          icon={Package}
          label="Items"
          loading={itemsCount.loading && !itemsCount.data}
          tone={itemsCount.error ? 'danger' : 'accent'}
          value={itemsCount.data ? formatNumber(itemsCount.data.total) : '—'}
          meta={itemsCount.error ? itemsCount.error.code : 'rows in the items table'}
          to="/items"
        />
      </div>

      <div className={styles.grid}>
        <ProviderChainCard data={providers.data} error={providers.error} loading={providers.loading} onRetry={providers.refetch} />
        <ConnectionCard health={health.data} />
      </div>

      <h2 className={styles.sectionTitle}>Explore the demos</h2>
      <div className={styles.explore}>
        {NAV_ITEMS.filter((n) => n.to !== '/').map(({ to, label, icon: Icon, description }) => (
          <Link key={to} to={to} className={styles.exploreCard}>
            <span className={styles.exploreIcon}>
              <Icon size={18} aria-hidden="true" />
            </span>
            <span className={styles.exploreText}>
              <span className={styles.exploreTitle}>{label}</span>
              <span className={styles.exploreDesc}>{description}</span>
            </span>
            <ArrowRight size={16} className={styles.exploreArrow} aria-hidden="true" />
          </Link>
        ))}
      </div>
    </>
  )
}
