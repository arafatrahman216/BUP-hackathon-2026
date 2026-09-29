import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Plus } from 'lucide-react'
import { describe, expect, it, vi } from 'vitest'
import { Button } from './Button'

describe('Button', () => {
  it('fires onClick', async () => {
    const onClick = vi.fn()
    render(
      <Button leftIcon={Plus} onClick={onClick}>
        Save
      </Button>,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('shows a spinner and is disabled while loading', async () => {
    const onClick = vi.fn()
    render(
      <Button loading onClick={onClick}>
        Save
      </Button>,
    )
    const button = screen.getByRole('button', { name: /save/i })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument()
    await userEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('defaults to type="button" so it never submits forms by accident', () => {
    render(<Button>Plain</Button>)
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button')
  })
})
