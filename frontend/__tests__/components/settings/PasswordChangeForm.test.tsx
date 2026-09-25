/**
 * PasswordChangeForm Component Tests
 * Story P10-1.1: Implement Admin Password Change
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PasswordChangeForm } from '@/components/settings/PasswordChangeForm';
import { apiClient } from '@/lib/api-client';

// Mock the API client
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    auth: {
      changePassword: vi.fn(),
    },
  },
}));

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { toast } from 'sonner';

describe('PasswordChangeForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders all password fields', () => {
    render(<PasswordChangeForm />);

    expect(screen.getByPlaceholderText(/enter your current password/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/enter your new password/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/confirm your new password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /change password/i })).toBeInTheDocument();
  });

  it('shows password visibility toggle buttons', () => {
    render(<PasswordChangeForm />);

    // There should be 3 visibility toggle buttons (one per field)
    const toggleButtons = screen.getAllByRole('button', { name: /show|hide/i });
    expect(toggleButtons).toHaveLength(3);
  });

  it('toggles password visibility when clicking eye icon', async () => {
    const user = userEvent.setup();
    render(<PasswordChangeForm />);

    const currentPasswordInput = screen.getByPlaceholderText(/enter your current password/i);
    expect(currentPasswordInput).toHaveAttribute('type', 'password');

    // Click the first toggle button (for current password)
    const toggleButton = screen.getByRole('button', { name: /show current password/i });
    await user.click(toggleButton);

    expect(currentPasswordInput).toHaveAttribute('type', 'text');
  });

  it('shows validation error when current password is empty', async () => {
    const user = userEvent.setup();
    render(<PasswordChangeForm />);

    const submitButton = screen.getByRole('button', { name: /^change password$/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/current password is required/i)).toBeInTheDocument();
    });
  });

  it('shows validation error for weak password', async () => {
    const user = userEvent.setup();
    render(<PasswordChangeForm />);

    const currentPasswordInput = screen.getByPlaceholderText(/enter your current password/i);
    const newPasswordInput = screen.getByPlaceholderText(/enter your new password/i);
    const confirmPasswordInput = screen.getByPlaceholderText(/confirm your new password/i);

    await user.type(currentPasswordInput, 'currentpass');
    await user.type(newPasswordInput, 'weak'); // Too short, no uppercase, no number, no special char
    await user.type(confirmPasswordInput, 'weak');

    const submitButton = screen.getByRole('button', { name: /^change password$/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/password must be at least 8 characters/i)).toBeInTheDocument();
    });
  });

  it('shows validation error when passwords do not match', async () => {
    const user = userEvent.setup();
    render(<PasswordChangeForm />);

    const currentPasswordInput = screen.getByPlaceholderText(/enter your current password/i);
    const newPasswordInput = screen.getByPlaceholderText(/enter your new password/i);
    const confirmPasswordInput = screen.getByPlaceholderText(/confirm your new password/i);

    await user.type(currentPasswordInput, 'currentpass');
    await user.type(newPasswordInput, 'ValidP@ss1');
    await user.type(confirmPasswordInput, 'DifferentP@ss1');

    const submitButton = screen.getByRole('button', { name: /^change password$/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
    });
  });

  it('shows password strength indicator when typing new password', async () => {
    const user = userEvent.setup();
    render(<PasswordChangeForm />);

    const newPasswordInput = screen.getByPlaceholderText(/enter your new password/i);
    await user.type(newPasswordInput, 'Test');

    // Should show password requirements
    await waitFor(() => {
      expect(screen.getByText(/password requirements/i)).toBeInTheDocument();
      expect(screen.getByText(/at least 8 characters/i)).toBeInTheDocument();
      expect(screen.getByText(/at least 1 uppercase letter/i)).toBeInTheDocument();
      expect(screen.getByText(/at least 1 number/i)).toBeInTheDocument();
      expect(screen.getByText(/at least 1 special character/i)).toBeInTheDocument();
    });
  });

  it('submits form successfully with valid data', async () => {
    const user = userEvent.setup();
    vi.mocked(apiClient.auth.changePassword).mockResolvedValueOnce({
      message: 'Password changed successfully',
    });

    render(<PasswordChangeForm />);

    const currentPasswordInput = screen.getByPlaceholderText(/enter your current password/i);
    const newPasswordInput = screen.getByPlaceholderText(/enter your new password/i);
    const confirmPasswordInput = screen.getByPlaceholderText(/confirm your new password/i);

    await user.type(currentPasswordInput, 'OldPassword123!');
    await user.type(newPasswordInput, 'NewPassword456!');
    await user.type(confirmPasswordInput, 'NewPassword456!');

    const submitButton = screen.getByRole('button', { name: /^change password$/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(apiClient.auth.changePassword).toHaveBeenCalledWith({
        current_password: 'OldPassword123!',
        new_password: 'NewPassword456!',
      });
      expect(toast.success).toHaveBeenCalledWith('Password updated successfully');
    });
  });

  it('shows error toast when current password is incorrect', async () => {
    const user = userEvent.setup();
    vi.mocked(apiClient.auth.changePassword).mockRejectedValueOnce(
      new Error('Current password is incorrect')
    );

    render(<PasswordChangeForm />);

    const currentPasswordInput = screen.getByPlaceholderText(/enter your current password/i);
    const newPasswordInput = screen.getByPlaceholderText(/enter your new password/i);
    const confirmPasswordInput = screen.getByPlaceholderText(/confirm your new password/i);

    await user.type(currentPasswordInput, 'WrongPassword123!');
    await user.type(newPasswordInput, 'NewPassword456!');
    await user.type(confirmPasswordInput, 'NewPassword456!');

    const submitButton = screen.getByRole('button', { name: /^change password$/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Current password is incorrect');
    });
  });

  it('shows loading state while submitting', async () => {
    const user = userEvent.setup();
    // Create a promise that we can control
    let resolvePromise: (value: { message: string }) => void;
    const promise = new Promise<{ message: string }>((resolve) => {
      resolvePromise = resolve;
    });
    vi.mocked(apiClient.auth.changePassword).mockReturnValueOnce(promise);

    render(<PasswordChangeForm />);

    const currentPasswordInput = screen.getByPlaceholderText(/enter your current password/i);
    const newPasswordInput = screen.getByPlaceholderText(/enter your new password/i);
    const confirmPasswordInput = screen.getByPlaceholderText(/confirm your new password/i);

    await user.type(currentPasswordInput, 'OldPassword123!');
    await user.type(newPasswordInput, 'NewPassword456!');
    await user.type(confirmPasswordInput, 'NewPassword456!');

    const submitButton = screen.getByRole('button', { name: /^change password$/i });
    await user.click(submitButton);

    // Button should be disabled while loading
    expect(submitButton).toBeDisabled();

    // Resolve the promise to complete the test
    resolvePromise!({ message: 'Success' });
    await waitFor(() => {
      expect(submitButton).not.toBeDisabled();
    });
  });

  it('keeps password entries and explains a CSRF rejection', async () => {
    const user = userEvent.setup();
    const csrfError = new Error('Request origin is not allowed');
    Object.assign(csrfError, { errorCode: 'CSRF_ORIGIN_DENIED' });
    vi.mocked(apiClient.auth.changePassword).mockRejectedValueOnce(csrfError);

    render(<PasswordChangeForm />);

    const currentPasswordInput = screen.getByPlaceholderText(/enter your current password/i) as HTMLInputElement;
    const newPasswordInput = screen.getByPlaceholderText(/enter your new password/i) as HTMLInputElement;
    const confirmPasswordInput = screen.getByPlaceholderText(/confirm your new password/i) as HTMLInputElement;

    await user.type(currentPasswordInput, 'OldPassword123!');
    await user.type(newPasswordInput, 'NewPassword456!');
    await user.type(confirmPasswordInput, 'NewPassword456!');

    await user.click(screen.getByRole('button', { name: /^change password$/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringMatching(/your entries are still here/i),
      );
    });
    expect(currentPasswordInput.value).toBe('OldPassword123!');
    expect(newPasswordInput.value).toBe('NewPassword456!');
    expect(confirmPasswordInput.value).toBe('NewPassword456!');
  });

  it('clears form after successful password change', async () => {
    const user = userEvent.setup();
    vi.mocked(apiClient.auth.changePassword).mockResolvedValueOnce({
      message: 'Password changed successfully',
    });

    render(<PasswordChangeForm />);

    const currentPasswordInput = screen.getByPlaceholderText(/enter your current password/i) as HTMLInputElement;
    const newPasswordInput = screen.getByPlaceholderText(/enter your new password/i) as HTMLInputElement;
    const confirmPasswordInput = screen.getByPlaceholderText(/confirm your new password/i) as HTMLInputElement;

    await user.type(currentPasswordInput, 'OldPassword123!');
    await user.type(newPasswordInput, 'NewPassword456!');
    await user.type(confirmPasswordInput, 'NewPassword456!');

    const submitButton = screen.getByRole('button', { name: /^change password$/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(currentPasswordInput.value).toBe('');
      expect(newPasswordInput.value).toBe('');
      expect(confirmPasswordInput.value).toBe('');
    });
  });
});
