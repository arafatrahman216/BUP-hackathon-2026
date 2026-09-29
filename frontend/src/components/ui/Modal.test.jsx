import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { Button } from './Button'
import { Modal } from './Modal'

function Harness({ onClose = () => {}, dismissible = true }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button onClick={() => setOpen(true)}>Open</Button>
      <Modal
        open={open}
        dismissible={dismissible}
        onClose={() => {
          onClose()
          setOpen(false)
        }}
        title="Edit item"
        footer={<Button>Save</Button>}
      >
        <input aria-label="Name" />
      </Modal>
    </>
  )
}

describe('Modal', () => {
  it('opens as an accessible dialog and focuses the first field', async () => {
    render(<Harness />)
    await userEvent.click(screen.getByRole('button', { name: 'Open' }))
    const dialog = screen.getByRole('dialog', { name: 'Edit item' })
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByLabelText('Name')).toHaveFocus()
  })

  it('closes on Escape and restores focus to the trigger', async () => {
    const onClose = vi.fn()
    render(<Harness onClose={onClose} />)
    const trigger = screen.getByRole('button', { name: 'Open' })
    await userEvent.click(trigger)
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledOnce()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('ignores Escape while not dismissible', async () => {
    const onClose = vi.fn()
    render(<Harness onClose={onClose} dismissible={false} />)
    await userEvent.click(screen.getByRole('button', { name: 'Open' }))
    await userEvent.keyboard('{Escape}')
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('traps Tab focus inside the dialog', async () => {
    render(<Harness />)
    await userEvent.click(screen.getByRole('button', { name: 'Open' }))
    const buttons = screen.getAllByRole('button').filter((b) => screen.getByRole('dialog').contains(b))
    buttons.at(-1).focus() // "Save" in the footer
    await userEvent.tab()
    expect(screen.getByRole('button', { name: 'Close dialog' })).toHaveFocus()
  })
})
