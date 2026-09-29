import { itemsApi } from '../api/api'
import { useAsync } from './useAsync'
import { useMutation } from './useMutation'

/**
 * Everything the Items page needs: the current page of items plus mutations
 * that refetch the list when they succeed. Copy this file for a new resource.
 *
 * @param {{page?: number, pageSize?: number, search?: string, isActive?: boolean | null}} query
 */
export function useItems({ page = 1, pageSize = 10, search = '', isActive = null } = {}) {
  const list = useAsync(
    ({ signal }) => itemsApi.list({ page, page_size: pageSize, search: search.trim(), is_active: isActive }, { signal }),
    [page, pageSize, search, isActive],
  )

  const refetch = list.refetch

  const create = useMutation(itemsApi.create, {
    successMessage: (item) => `“${item.name}” created`,
    errorToast: (error) => !error.isValidationError && error.code !== 'CONFLICT', // the form shows those inline
    onSuccess: refetch,
  })

  const update = useMutation(itemsApi.update, {
    successMessage: (item) => `“${item.name}” updated`,
    errorToast: (error) => !error.isValidationError && error.code !== 'CONFLICT',
    onSuccess: refetch,
  })

  const toggleActive = useMutation((item) => itemsApi.update(item.id, { is_active: !item.is_active }), {
    successMessage: (item) => `“${item.name}” is now ${item.is_active ? 'active' : 'inactive'}`,
    onSuccess: (updated) => list.setData((d) => d && { ...d, items: d.items.map((i) => (i.id === updated.id ? updated : i)) }),
  })

  const remove = useMutation((item) => itemsApi.remove(item.id), {
    successMessage: (_data, item) => `“${item.name}” deleted`,
    onSuccess: refetch,
  })

  const generateDescription = useMutation((item) => itemsApi.generateDescription(item.id), {
    successMessage: 'Description generated with AI',
    onSuccess: (updated) => list.setData((d) => d && { ...d, items: d.items.map((i) => (i.id === updated.id ? updated : i)) }),
  })

  return {
    items: list.data?.items ?? [],
    total: list.data?.total ?? 0,
    pages: list.data?.pages ?? 0,
    loading: list.loading,
    error: list.error,
    initialLoading: list.loading && !list.data,
    refetch,
    create,
    update,
    toggleActive,
    remove,
    generateDescription,
  }
}
