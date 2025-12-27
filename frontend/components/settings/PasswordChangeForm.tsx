/**
 * Password Change Form Component
 * Story P10-1.1: Implement Admin Password Change
 *
 * Allows users to change their password through the Settings UI.
 * Validates current password and new password requirements.
 */

'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import { Eye, EyeOff, Loader2, Lock, CheckCircle2, XCircle } from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

// Password validation schema matching backend requirements
const passwordChangeSchema = z.object({
  currentPassword: z.string().min(1, 'Current password is required'),
  newPassword: z.string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Password must contain at least 1 uppercase letter')
    .regex(/[0-9]/, 'Password must contain at least 1 number')
    .regex(/[^A-Za-z0-9]/, 'Password must contain at least 1 special character'),
  confirmPassword: z.string().min(1, 'Please confirm your new password'),
}).refine(data => data.newPassword === data.confirmPassword, {
  message: 'Passwords do not match',
  path: ['confirmPassword'],
});

type PasswordChangeFormData = z.infer<typeof passwordChangeSchema>;

// Password strength requirements for visual feedback
const passwordRequirements = [
  { regex: /.{8,}/, label: 'At least 8 characters' },
  { regex: /[A-Z]/, label: 'At least 1 uppercase letter' },
  { regex: /[0-9]/, label: 'At least 1 number' },
  { regex: /[^A-Za-z0-9]/, label: 'At least 1 special character' },
];

export function PasswordChangeForm() {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const form = useForm<PasswordChangeFormData>({
    resolver: zodResolver(passwordChangeSchema),
    defaultValues: {
      currentPassword: '',
      newPassword: '',
      confirmPassword: '',
    },
  });

  const { register, handleSubmit, formState: { errors }, watch, reset } = form;
  const newPassword = watch('newPassword');

  const onSubmit = async (data: PasswordChangeFormData) => {
    console.log('PasswordChangeForm: onSubmit called');
    try {
      setIsSubmitting(true);
      console.log('PasswordChangeForm: calling API...');
      const response = await apiClient.auth.changePassword({
        current_password: data.currentPassword,
        new_password: data.newPassword,
      });
      console.log('PasswordChangeForm: API response:', response);
      toast.success('Password updated successfully');
      reset(); // Clear form on success
    } catch (error) {
      console.error('PasswordChangeForm: API error:', error);
      // Handle specific error messages from backend
      if (error instanceof Error) {
        const message = error.message.toLowerCase();
        if (message.includes('incorrect') || message.includes('current password')) {
          toast.error('Current password is incorrect');
        } else if (message.includes('8 characters') || message.includes('uppercase') ||
                   message.includes('number') || message.includes('special')) {
          toast.error(error.message);
        } else {
          toast.error('Failed to change password. Please try again.');
        }
      } else {
        toast.error('Failed to change password. Please try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Lock className="h-5 w-5 text-muted-foreground" />
          <CardTitle>Change Password</CardTitle>
        </div>
        <CardDescription>
          Update your account password. You&apos;ll need to enter your current password to confirm changes.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Current Password */}
          <div className="space-y-2">
            <Label htmlFor="currentPassword">Current Password</Label>
            <div className="relative">
              <Input
                id="currentPassword"
                type={showCurrentPassword ? 'text' : 'password'}
                placeholder="Enter your current password"
                autoComplete="current-password"
                {...register('currentPassword')}
                className={errors.currentPassword ? 'border-destructive' : ''}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                aria-label={showCurrentPassword ? 'Hide current password' : 'Show current password'}
              >
                {showCurrentPassword ? (
                  <EyeOff className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <Eye className="h-4 w-4 text-muted-foreground" />
                )}
              </Button>
            </div>
            {errors.currentPassword && (
              <p className="text-sm text-destructive">{errors.currentPassword.message}</p>
            )}
          </div>

          {/* New Password */}
          <div className="space-y-2">
            <Label htmlFor="newPassword">New Password</Label>
            <div className="relative">
              <Input
                id="newPassword"
                type={showNewPassword ? 'text' : 'password'}
                placeholder="Enter your new password"
                autoComplete="new-password"
                {...register('newPassword')}
                className={errors.newPassword ? 'border-destructive' : ''}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                onClick={() => setShowNewPassword(!showNewPassword)}
                aria-label={showNewPassword ? 'Hide new password' : 'Show new password'}
              >
                {showNewPassword ? (
                  <EyeOff className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <Eye className="h-4 w-4 text-muted-foreground" />
                )}
              </Button>
            </div>
            {errors.newPassword && (
              <p className="text-sm text-destructive">{errors.newPassword.message}</p>
            )}

            {/* Password Strength Indicator */}
            {newPassword && (
              <div className="mt-2 space-y-1">
                <p className="text-xs text-muted-foreground font-medium">Password requirements:</p>
                <ul className="text-xs space-y-1">
                  {passwordRequirements.map((req, index) => {
                    const met = req.regex.test(newPassword);
                    return (
                      <li key={index} className={`flex items-center gap-1 ${met ? 'text-green-600' : 'text-muted-foreground'}`}>
                        {met ? (
                          <CheckCircle2 className="h-3 w-3" />
                        ) : (
                          <XCircle className="h-3 w-3" />
                        )}
                        {req.label}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </div>

          {/* Confirm New Password */}
          <div className="space-y-2">
            <Label htmlFor="confirmPassword">Confirm New Password</Label>
            <div className="relative">
              <Input
                id="confirmPassword"
                type={showConfirmPassword ? 'text' : 'password'}
                placeholder="Confirm your new password"
                autoComplete="new-password"
                {...register('confirmPassword')}
                className={errors.confirmPassword ? 'border-destructive' : ''}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
              >
                {showConfirmPassword ? (
                  <EyeOff className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <Eye className="h-4 w-4 text-muted-foreground" />
                )}
              </Button>
            </div>
            {errors.confirmPassword && (
              <p className="text-sm text-destructive">{errors.confirmPassword.message}</p>
            )}
          </div>

          {/* Submit Button */}
          <Button type="submit" disabled={isSubmitting} className="w-full sm:w-auto">
            {isSubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Change Password
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
