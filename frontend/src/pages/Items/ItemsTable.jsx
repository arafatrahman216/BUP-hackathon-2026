import { Pencil, Sparkles, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Badge } from '../../components/ui/Badge'
import { Button } from '../../components/ui/Button'
import { Switch } from '../../components/ui/Switch'
import { Table } from '../../components/ui/Table'
import { formatCurrency, formatDateTime, formatRelative } from '../../utils/format'
import styles from './ItemsTable.module.css'

export function ItemsTable({ items, loading, initialLoading, onEdit, onDelete, onToggleActive, onGenerate, empty }) {
  const [generatingId, setGeneratingId] = useState(null)
  const [togglingId, setTogglingId] = useState(null)

  const generate = async (item) => {
    setGeneratingId(item.id)
    await onGenerate(item)
    setGeneratingId(null)
  }

  const toggle = async (item) => {
    setTogglingId(item.id)
    await onToggleActive(item)
    setTogglingId(null)
  }

  const columns = [
    {
      key: 'name',
      header: 'Item',
      render: (item) => (
        <div className={styles.nameCell}>
          <span className={styles.name}>{item.name}</span>
          {item.description ? (
            <span className={styles.description} title={item.description}>
              {item.description}
            </span>
          ) : (
            <span className={styles.noDescription}>No description</span>
          )}
        </div>
      ),
    },
    {
      key: 'price',
      header: 'Price',
      align: 'right',
      width: 110,
      render: (item) => <span className={styles.price}>{formatCurrency(item.price)}</span>,
    },
    {
      key: 'status',
      header: 'Status',
      width: 150,
      hideOnMobile: true,
      render: (item) => (
        <div className={styles.status}>
          <Switch size="sm" checked={item.is_active} onChange={() => toggle(item)} disabled={togglingId === item.id} aria-label={`${item.is_active ? 'Deactivate' : 'Activate'} ${item.name}`} />
          <Badge variant={item.is_active ? 'success' : 'neutral'} dot>
            {item.is_active ? 'Active' : 'Inactive'}
          </Badge>
        </div>
      ),
    },
    {
      key: 'updated',
      header: 'Updated',
      width: 140,
      hideOnMobile: true,
      render: (item) => (
        <time dateTime={item.updated_at} title={formatDateTime(item.updated_at)} className={styles.muted}>
          {formatRelative(item.updated_at)}
        </time>
      ),
    },
    {
      key: 'actions',
      header: <span className="sr-only">Actions</span>,
      width: 124,
      align: 'right',
      render: (item) => (
        <div className={styles.actions}>
          <Button
            size="sm"
            variant="ghost"
            iconOnly
            leftIcon={Sparkles}
            loading={generatingId === item.id}
            onClick={() => generate(item)}
            aria-label={`Generate description for ${item.name} with AI`}
            title="Generate description with AI"
          />
          <Button size="sm" variant="ghost" iconOnly leftIcon={Pencil} onClick={() => onEdit(item)} aria-label={`Edit ${item.name}`} title="Edit" />
          <Button size="sm" variant="ghost" iconOnly leftIcon={Trash2} onClick={() => onDelete(item)} aria-label={`Delete ${item.name}`} title="Delete" className={styles.danger} />
        </div>
      ),
    },
  ]

  return <Table caption="Items" columns={columns} rows={items} loading={initialLoading} dimmed={loading && !initialLoading} empty={empty} skeletonRows={6} />
}
