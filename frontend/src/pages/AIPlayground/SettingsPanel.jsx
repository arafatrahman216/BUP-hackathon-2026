import { SlidersHorizontal } from 'lucide-react'
import { Card } from '../../components/ui/Card'
import { ErrorState } from '../../components/ui/ErrorState'
import { Input } from '../../components/ui/Input'
import { Select } from '../../components/ui/Select'
import { Switch } from '../../components/ui/Switch'
import { Textarea } from '../../components/ui/Textarea'
import styles from './SettingsPanel.module.css'

export function SettingsPanel({ settings, onChange, providers }) {
  const set = (key) => (value) => onChange((s) => ({ ...s, [key]: value }))
  const list = providers.data?.providers ?? []
  const selected = list.find((p) => p.name === settings.provider)
  const chain = providers.data?.active_chain ?? []

  const options = [
    { value: '', label: 'Auto (fallback chain)' },
    ...list.map((p) => ({ value: p.name, label: `${p.name}${p.configured ? '' : ' (no API key)'}` })),
  ]

  return (
    <Card icon={SlidersHorizontal} title="Settings" description="Sent with every message." className={styles.panel}>
      <div className={styles.form}>
        {providers.error && <ErrorState error={providers.error} onRetry={providers.refetch} compact />}

        <Select
          label="Provider"
          options={options}
          value={settings.provider}
          onChange={(e) => onChange((s) => ({ ...s, provider: e.target.value, model: '' }))}
          disabled={providers.loading && !providers.data}
          hint={settings.provider ? 'Only this provider is called (no fallback).' : chain.length ? `Tries ${chain.join(' → ')} in order.` : 'Tries each configured provider in order.'}
        />

        {settings.provider && (
          <Input label="Model" value={settings.model} onChange={(e) => set('model')(e.target.value)} placeholder={selected?.default_model || 'provider default'} hint="Leave empty for the provider's default." inputClassName="mono" />
        )}

        <div className={styles.range}>
          <div className={styles.rangeHead}>
            <label htmlFor="temperature">Temperature</label>
            <output htmlFor="temperature" className={styles.rangeValue}>
              {settings.temperature.toFixed(1)}
            </output>
          </div>
          <input id="temperature" type="range" min="0" max="2" step="0.1" value={settings.temperature} onChange={(e) => set('temperature')(Number(e.target.value))} className={styles.slider} />
          <div className={styles.rangeScale} aria-hidden="true">
            <span>Precise</span>
            <span>Creative</span>
          </div>
        </div>

        <Input label="Max tokens" type="number" min="1" max="65536" inputMode="numeric" value={settings.maxTokens} onChange={(e) => set('maxTokens')(e.target.value)} placeholder="Provider default" />

        <Switch checked={settings.jsonMode} onChange={set('jsonMode')} label="JSON mode" description="Ask for a JSON object; replies are pretty-printed." />

        <Textarea label="System prompt" rows={3} value={settings.system} onChange={(e) => set('system')(e.target.value)} placeholder="You are a helpful assistant…" />
      </div>
    </Card>
  )
}
