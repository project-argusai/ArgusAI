/**
 * Button Component Tests
 *
 * Demonstrates basic component testing patterns:
 * - Simple rendering
 * - Props testing
 * - User interactions
 * - Variants and styles
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Button } from '@/components/ui/button'

describe('Button', () => {
  describe('rendering', () => {
    it('renders with default props', () => {
      render(<Button>Click me</Button>)

      const button = screen.getByRole('button', { name: /click me/i })
      expect(button).toBeInTheDocument()
    })

    it('renders children correctly', () => {
      render(<Button>Test Button Text</Button>)

      expect(screen.getByText('Test Button Text')).toBeInTheDocument()
    })

    it('renders with custom className', () => {
      render(<Button className="custom-class">Button</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('custom-class')
    })
  })

  describe('variants', () => {
    it('renders default variant', () => {
      render(<Button variant="default">Default</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('bg-primary')
    })

    it('renders destructive variant', () => {
      render(<Button variant="destructive">Delete</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('bg-destructive')
    })

    it('renders outline variant', () => {
      render(<Button variant="outline">Outline</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('border')
    })

    it('renders ghost variant', () => {
      render(<Button variant="ghost">Ghost</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('hover:bg-accent')
    })
  })

  describe('sizes', () => {
    it('renders default size', () => {
      render(<Button size="default">Default Size</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('h-9')
    })

    it('renders small size', () => {
      render(<Button size="sm">Small</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('h-8')
    })

    it('renders large size', () => {
      render(<Button size="lg">Large</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('h-10')
    })

    it('renders icon size', () => {
      render(<Button size="icon">X</Button>)

      const button = screen.getByRole('button')
      expect(button).toHaveClass('size-9')
    })
  })

  describe('interactions', () => {
    it('handles click events', async () => {
      const handleClick = vi.fn()
      const user = userEvent.setup()

      render(<Button onClick={handleClick}>Clickable</Button>)

      const button = screen.getByRole('button')
      await user.click(button)

      expect(handleClick).toHaveBeenCalledTimes(1)
    })

    it('does not fire click when disabled', async () => {
      const handleClick = vi.fn()
      const user = userEvent.setup()

      render(
        <Button onClick={handleClick} disabled>
          Disabled
        </Button>
      )

      const button = screen.getByRole('button')
      await user.click(button)

      expect(handleClick).not.toHaveBeenCalled()
    })

    it('applies disabled styles', () => {
      render(<Button disabled>Disabled Button</Button>)

      const button = screen.getByRole('button')
      expect(button).toBeDisabled()
      expect(button).toHaveClass('disabled:opacity-50')
    })
  })

  describe('accessibility', () => {
    it('is focusable', async () => {
      const user = userEvent.setup()

      render(<Button>Focus Me</Button>)

      const button = screen.getByRole('button')
      await user.tab()

      expect(button).toHaveFocus()
    })

    it('can be activated with keyboard', async () => {
      const handleClick = vi.fn()
      const user = userEvent.setup()

      render(<Button onClick={handleClick}>Press Enter</Button>)

      const button = screen.getByRole('button')
      button.focus()
      await user.keyboard('{Enter}')

      expect(handleClick).toHaveBeenCalled()
    })

    it('supports aria-label', () => {
      render(<Button aria-label="Close dialog">X</Button>)

      const button = screen.getByRole('button', { name: /close dialog/i })
      expect(button).toBeInTheDocument()
    })
  })

  describe('asChild prop', () => {
    it('renders as child element when asChild is true', () => {
      render(
        <Button asChild>
          <a href="/test">Link Button</a>
        </Button>
      )

      const link = screen.getByRole('link', { name: /link button/i })
      expect(link).toBeInTheDocument()
      expect(link).toHaveAttribute('href', '/test')
    })
  })
})
