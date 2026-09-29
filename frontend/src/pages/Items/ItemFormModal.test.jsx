import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../../api/api'
import { renderWithProviders } from '../../test/utils'
import { ItemFormModal } from './ItemFormModal'

describe('ItemFormModal', () => {
  it('validates on the client before calling the API', async () => {
    const onSubmit = vi.fn()
    renderWithProviders(<ItemFormModal open onClose={() => {}} onSubmit={onSubmit} />)
    await userEvent.click(screen.getByRole('button', { name: 'Create item' }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByText('Name is required')).toBeInTheDocument()
  })

  it('shows server-side field errors under the matching input', async () => {
    const error = new ApiError({ status: 409, code: 'CONFLICT', message: 'Item name already exists', details: { field: 'name' } })
    const onSubmit = vi.fn().mockResolvedValue({ data: null, error })
    renderWithProviders(<ItemFormModal open onClose={() => {}} onSubmit={onSubmit} />)

    await userEvent.type(screen.getByLabelText(/name/i), 'Keyboard')
    await userEvent.click(screen.getByRole('button', { name: 'Create item' }))

    expect(onSubmit).toHaveBeenCalledWith({ name: 'Keyboard', description: null, price: 0, is_active: true })
    expect(await screen.findByText('Item name already exists')).toBeInTheDocument()
    expect(screen.getByLabelText(/name/i)).toHaveAttribute('aria-invalid', 'true')
  })
})
