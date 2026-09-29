import { Check, Copy, ExternalLink, File, FileArchive, FileAudio, FileImage, FileText, FileVideo, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { filesApi } from '../../api/api'
import { Button } from '../../components/ui/Button'
import { Table } from '../../components/ui/Table'
import { useCopyToClipboard } from '../../hooks/useCopyToClipboard'
import { useToast } from '../../hooks/useToast'
import { getErrorMessage } from '../../utils/errors'
import { formatBytes, formatDateTime, formatRelative } from '../../utils/format'
import styles from './FilesTable.module.css'

function iconFor(type = '') {
  if (type.startsWith('image/')) return FileImage
  if (type.startsWith('video/')) return FileVideo
  if (type.startsWith('audio/')) return FileAudio
  if (type.includes('zip') || type.includes('compressed') || type.includes('tar')) return FileArchive
  if (type.startsWith('text/') || type.includes('pdf') || type.includes('json') || type.includes('document')) return FileText
  return File
}

export function FilesTable({ files, loading, dimmed, onDelete, empty }) {
  const { toast } = useToast()
  const { copy } = useCopyToClipboard()
  const [busy, setBusy] = useState(null) // `${action}:${path}`
  const [copiedPath, setCopiedPath] = useState(null)

  const copyLink = async (file) => {
    setBusy(`copy:${file.path}`)
    try {
      const { signed_url: url, expires_in: expiresIn } = await filesApi.signedUrl(file.path, 3600)
      if (await copy(url)) {
        setCopiedPath(file.path)
        setTimeout(() => setCopiedPath((p) => (p === file.path ? null : p)), 1800)
        toast.success('Signed URL copied', { description: `Valid for ${Math.round(expiresIn / 60)} minutes.` })
      } else {
        toast.error('Could not access the clipboard')
      }
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setBusy(null)
    }
  }

  const open = async (file) => {
    // Open the tab synchronously so the popup blocker allows it, then navigate.
    const tab = window.open('about:blank', '_blank')
    if (tab) tab.opener = null
    setBusy(`open:${file.path}`)
    try {
      const { signed_url: url } = await filesApi.signedUrl(file.path, 600)
      if (tab) tab.location.href = url
      else window.location.assign(url)
    } catch (error) {
      tab?.close()
      toast.error(getErrorMessage(error))
    } finally {
      setBusy(null)
    }
  }

  const columns = [
    {
      key: 'name',
      header: 'Name',
      render: (file) => {
        const Icon = iconFor(file.content_type || '')
        return (
          <div className={styles.nameCell}>
            <span className={styles.fileIcon}>
              <Icon size={16} aria-hidden="true" />
            </span>
            <div className={styles.nameText}>
              <span className={styles.name} title={file.name}>
                {file.name}
              </span>
              <span className={styles.meta}>
                {formatBytes(file.size)}
                <span className={styles.metaMobile}> · {formatRelative(file.created_at)}</span>
              </span>
            </div>
          </div>
        )
      },
    },
    { key: 'type', header: 'Type', width: 150, hideOnMobile: true, render: (file) => <span className={styles.type}>{file.content_type || '—'}</span> },
    {
      key: 'created',
      header: 'Uploaded',
      width: 130,
      hideOnMobile: true,
      render: (file) => (
        <time className={styles.muted} dateTime={file.created_at ?? undefined} title={formatDateTime(file.created_at)}>
          {formatRelative(file.created_at)}
        </time>
      ),
    },
    {
      key: 'actions',
      header: <span className="sr-only">Actions</span>,
      width: 124,
      align: 'right',
      render: (file) => (
        <div className={styles.actions}>
          <Button
            size="sm"
            variant="ghost"
            iconOnly
            leftIcon={copiedPath === file.path ? Check : Copy}
            loading={busy === `copy:${file.path}`}
            onClick={() => copyLink(file)}
            aria-label={`Copy signed URL for ${file.name}`}
            title="Copy signed URL (1 hour)"
          />
          <Button size="sm" variant="ghost" iconOnly leftIcon={ExternalLink} loading={busy === `open:${file.path}`} onClick={() => open(file)} aria-label={`Open ${file.name}`} title="Open in new tab" />
          <Button size="sm" variant="ghost" iconOnly leftIcon={Trash2} onClick={() => onDelete(file)} aria-label={`Delete ${file.name}`} title="Delete" className={styles.danger} />
        </div>
      ),
    },
  ]

  return <Table caption="Files" columns={columns} rows={files} rowKey="path" loading={loading} dimmed={dimmed} empty={empty} skeletonRows={4} />
}
