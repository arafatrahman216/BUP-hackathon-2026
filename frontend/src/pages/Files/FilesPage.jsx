import { FolderOpen, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { ConfirmDialog } from '../../components/ui/ConfirmDialog'
import { EmptyState } from '../../components/ui/EmptyState'
import { ErrorState } from '../../components/ui/ErrorState'
import { Input } from '../../components/ui/Input'
import { useDebounce } from '../../hooks/useDebounce'
import { useFiles } from '../../hooks/useFiles'
import { useToast } from '../../hooks/useToast'
import { Dropzone } from './Dropzone'
import styles from './FilesPage.module.css'
import { FilesTable } from './FilesTable'
import { UploadQueue } from './UploadQueue'

const cleanFolder = (value) => value.trim().replace(/^\/+|\/+$/g, '') || 'uploads'

export default function FilesPage() {
  const [folderInput, setFolderInput] = useState('uploads')
  const folder = cleanFolder(useDebounce(folderInput, 400))
  const files = useFiles(folder)
  const { toast } = useToast()
  const [deleting, setDeleting] = useState(null)

  const handleFiles = async (list) => {
    const { succeeded, failed } = await files.upload(list, folder)
    if (succeeded) toast.success(`Uploaded ${succeeded} file${succeeded === 1 ? '' : 's'} to ${folder}/`)
    if (failed) toast.error(`${failed} upload${failed === 1 ? '' : 's'} failed`, { description: 'See the upload list for details.' })
  }

  const confirmDelete = async () => {
    const { error } = await files.remove.mutate(deleting)
    if (!error) setDeleting(null)
  }

  return (
    <>
      <PageHeader
        icon={FolderOpen}
        title="Files"
        description="Upload files to Supabase Storage through the backend, list a folder, and share short-lived signed URLs. The service-role key never leaves the server."
        actions={
          <Button leftIcon={RefreshCw} onClick={files.refetch} loading={files.loading && !files.initialLoading}>
            Refresh
          </Button>
        }
      />

      <div className={styles.layout}>
        <Card title="Upload" description="Drag files in or browse. Max size is set by MAX_UPLOAD_MB (10 MB by default).">
          <div className={styles.uploadStack}>
            <Input label="Folder" value={folderInput} onChange={(e) => setFolderInput(e.target.value)} hint={`Files go to ${folder}/ and the list shows this folder.`} inputClassName="mono" />
            <Dropzone onFiles={handleFiles} disabled={files.uploading} />
            <UploadQueue uploads={files.uploads} onClear={files.clearUploads} />
          </div>
        </Card>

        <Card title={`${folder}/`} description={files.initialLoading ? 'Loading…' : `${files.files.length} file${files.files.length === 1 ? '' : 's'}`} padded={false}>
          {files.error ? (
            <div className={styles.errorWrap}>
              <ErrorState error={files.error} onRetry={files.refetch} retrying={files.loading} title={files.error.status >= 500 ? 'Storage unavailable' : undefined} />
              <p className={styles.errorHint}>
                Storage needs <code>SUPABASE_URL</code>, <code>SUPABASE_SERVICE_ROLE_KEY</code> and <code>SUPABASE_BUCKET_NAME</code> in <code>backend/.env</code>.
              </p>
            </div>
          ) : (
            <FilesTable
              files={files.files}
              loading={files.initialLoading}
              dimmed={files.loading && !files.initialLoading}
              onDelete={setDeleting}
              empty={<EmptyState compact icon={FolderOpen} title="This folder is empty" description="Uploaded files will show up here." />}
            />
          )}
        </Card>
      </div>

      <ConfirmDialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        onConfirm={confirmDelete}
        loading={files.remove.loading}
        title="Delete file?"
        message={
          <>
            <code>{deleting?.path}</code> will be removed from the bucket. Existing signed URLs stop working.
          </>
        }
        confirmLabel="Delete file"
      />
    </>
  )
}
