import { Package, Plus, Search } from 'lucide-react'
import { useState } from 'react'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { ConfirmDialog } from '../../components/ui/ConfirmDialog'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { Input } from '../../components/ui/Input'
import { Pagination } from '../../components/ui/Pagination'
import { Select } from '../../components/ui/Select'
import { useDebounce } from '../../hooks/useDebounce'
import { useItems } from '../../hooks/useItems'
import { ItemFormModal } from './ItemFormModal'
import styles from './ItemsPage.module.css'
import { ItemsTable } from './ItemsTable'

const PAGE_SIZE = 8
const STATUS_OPTIONS = [
  { value: 'all', label: 'All statuses' },
  { value: 'true', label: 'Active' },
  { value: 'false', label: 'Inactive' },
]

/**
 * The template's reference CRUD page. Pattern: page state (filters, which
 * modal is open) lives here; data + mutations come from a hook (useItems);
 * presentational pieces (table, form modal) live next to this file.
 */
export default function ItemsPage() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('all')
  const [editing, setEditing] = useState(null) // null = closed, {} = create, item = edit
  const [deleting, setDeleting] = useState(null)

  const debouncedSearch = useDebounce(search, 300)
  const isActive = status === 'all' ? null : status === 'true'
  const items = useItems({ page, pageSize: PAGE_SIZE, search: debouncedSearch, isActive })

  const hasFilters = Boolean(debouncedSearch) || status !== 'all'

  const handleSubmit = async (values) => {
    const result = editing?.id ? await items.update.mutate(editing.id, values) : await items.create.mutate(values)
    if (!result.error) setEditing(null)
    return result
  }

  const confirmDelete = async () => {
    const { error } = await items.remove.mutate(deleting)
    if (error) return
    setDeleting(null)
    if (items.items.length === 1 && page > 1) setPage(page - 1) // deleted the last row on this page
  }

  return (
    <>
      <PageHeader
        icon={Package}
        title="Items"
        description="A complete CRUD example: paginated list with search and filters, create/edit form with server-side validation, inline toggles, AI-generated descriptions and delete confirmation."
        actions={
          <Button variant="primary" leftIcon={Plus} onClick={() => setEditing({})}>
            New item
          </Button>
        }
      />

      <Card padded={false}>
        <div className={styles.toolbar}>
          <Input
            type="search"
            leftIcon={Search}
            placeholder="Search by name…"
            aria-label="Search items"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
            className={styles.search}
          />
          <Select aria-label="Filter by status" options={STATUS_OPTIONS} value={status} onChange={(e) => {
              setStatus(e.target.value)
              setPage(1)
            }} className={styles.filter} />
        </div>

        {items.error ? (
          <div className={styles.errorWrap}>
            <ErrorState error={items.error} onRetry={items.refetch} retrying={items.loading} />
          </div>
        ) : (
          <ItemsTable
            items={items.items}
            loading={items.loading}
            initialLoading={items.initialLoading}
            onEdit={setEditing}
            onDelete={setDeleting}
            onToggleActive={items.toggleActive.mutate}
            onGenerate={items.generateDescription.mutate}
            empty={
              hasFilters ? (
                <EmptyState
                  icon={Search}
                  title="No matching items"
                  description="Try a different search term or clear the filters."
                  action={
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setSearch('')
                        setStatus('all')
                        setPage(1)
                      }}
                    >
                      Clear filters
                    </Button>
                  }
                />
              ) : (
                <EmptyState
                  icon={Package}
                  title="No items yet"
                  description="Items are stored in the backend database. Create the first one to see the full flow."
                  action={
                    <Button variant="primary" leftIcon={Plus} onClick={() => setEditing({})}>
                      Create item
                    </Button>
                  }
                />
              )
            }
          />
        )}

        {items.total > 0 && !items.error && (
          <div className={styles.footer}>
            <Pagination page={page} pages={items.pages} total={items.total} pageSize={PAGE_SIZE} onPageChange={setPage} />
          </div>
        )}
      </Card>

      <ItemFormModal
        open={editing !== null}
        item={editing?.id ? editing : null}
        onClose={() => setEditing(null)}
        onSubmit={handleSubmit}
        submitting={items.create.loading || items.update.loading}
      />

      <ConfirmDialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        onConfirm={confirmDelete}
        loading={items.remove.loading}
        title="Delete item?"
        message={
          <>
            <strong>{deleting?.name}</strong> will be permanently removed. This can't be undone.
          </>
        }
        confirmLabel="Delete"
      />
    </>
  )
}
