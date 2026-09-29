import { useCallback, useState } from 'react'
import { filesApi } from '../api/api'
import { useAsync } from './useAsync'
import { useMutation } from './useMutation'

let uploadId = 0

/**
 * Supabase Storage files under `prefix`, plus an upload queue.
 * `upload(files)` sends them one by one and tracks each file's status.
 */
export function useFiles(prefix = 'uploads') {
  const list = useAsync(({ signal }) => filesApi.list({ prefix }, { signal }), [prefix])
  const [uploads, setUploads] = useState([])

  const remove = useMutation((file) => filesApi.remove(file.path), {
    successMessage: (_d, file) => `Deleted ${file.name}`,
    onSuccess: (_d, file) => list.setData((files) => (files ?? []).filter((f) => f.path !== file.path)),
  })

  const patch = (id, changes) => setUploads((list) => list.map((u) => (u.id === id ? { ...u, ...changes } : u)))

  const refetch = list.refetch
  const upload = useCallback(
    async (fileList, folder = prefix) => {
      const files = [...fileList]
      const entries = files.map((file) => ({ id: ++uploadId, name: file.name, size: file.size, status: 'queued', error: null }))
      setUploads((current) => [...entries, ...current].slice(0, 8))
      let succeeded = 0
      for (const [i, file] of files.entries()) {
        patch(entries[i].id, { status: 'uploading' })
        try {
          await filesApi.upload(file, { folder })
          patch(entries[i].id, { status: 'done' })
          succeeded += 1
        } catch (error) {
          patch(entries[i].id, { status: 'error', error })
        }
      }
      if (succeeded) refetch()
      return { succeeded, failed: files.length - succeeded }
    },
    [prefix, refetch],
  )

  const clearUploads = useCallback(() => setUploads((list) => list.filter((u) => u.status === 'uploading' || u.status === 'queued')), [])

  return {
    files: list.data ?? [],
    loading: list.loading,
    initialLoading: list.loading && !list.data,
    error: list.error,
    refetch,
    remove,
    upload,
    uploads,
    uploading: uploads.some((u) => u.status === 'uploading' || u.status === 'queued'),
    clearUploads,
  }
}
