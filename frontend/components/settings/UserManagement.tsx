/**
 * User Management Component (Story P15-2.10)
 *
 * Admin-only component for managing user accounts.
 * Features:
 * - Create new users with temporary passwords
 * - Edit user roles and status
 * - Reset passwords
 * - Delete users
 */

'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Users,
  Plus,
  Pencil,
  Trash2,
  Key,
  Copy,
  Check,
  X,
  Shield,
  Eye,
  UserCog,
  Loader2,
  Mail,
} from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import { formatLocale } from '@/lib/datetime';
import type { IUser, IUserCreate, IUserCreateResponse, UserRole } from '@/types/auth';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface UserManagementProps {
  currentUserId: string;
}

const roleIcons: Record<UserRole, React.ElementType> = {
  admin: Shield,
  operator: UserCog,
  viewer: Eye,
};

const roleColors: Record<UserRole, string> = {
  admin: 'bg-purple-500/10 text-purple-500 hover:bg-purple-500/20',
  operator: 'bg-blue-500/10 text-blue-500 hover:bg-blue-500/20',
  viewer: 'bg-gray-500/10 text-gray-500 hover:bg-gray-500/20',
};

const roleDescriptions: Record<UserRole, string> = {
  admin: 'Full system access including user management',
  operator: 'Manage events, entities, cameras but not users',
  viewer: 'Read-only access to dashboard and events',
};

export function UserManagement({ currentUserId }: UserManagementProps) {
  const queryClient = useQueryClient();
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<IUser | null>(null);
  const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null);
  const [copiedPassword, setCopiedPassword] = useState(false);

  // Form state for creating new user
  const [newUsername, setNewUsername] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newRole, setNewRole] = useState<UserRole>('viewer');
  const [sendEmail, setSendEmail] = useState(false);

  // Check if SMTP is configured for enabling email option
  const { data: smtpSettings } = useQuery({
    queryKey: ['smtp-config'],
    queryFn: () => apiClient.smtp.getSettings(),
  });

  // Form state for editing user
  const [editEmail, setEditEmail] = useState('');
  const [editRole, setEditRole] = useState<UserRole>('viewer');
  const [editIsActive, setEditIsActive] = useState(true);

  // Fetch users
  const { data: users, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: () => apiClient.users.list(),
  });

  // Create user mutation
  const createUserMutation = useMutation({
    mutationFn: (data: IUserCreate) => apiClient.users.create(data),
    onSuccess: (response: IUserCreateResponse) => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      // Only show password if email wasn't sent
      if (!sendEmail || !response.email_sent) {
        setTemporaryPassword(response.temporary_password);
      }
      setNewUsername('');
      setNewEmail('');
      setNewRole('viewer');
      setSendEmail(false);
      if (response.email_sent) {
        toast.success(`User "${response.username}" created and invitation email sent`);
      } else {
        toast.success(`User "${response.username}" created successfully`);
      }
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to create user');
    },
  });

  // Update user mutation
  const updateUserMutation = useMutation({
    mutationFn: ({ userId, data }: { userId: string; data: { email?: string; role?: UserRole; is_active?: boolean } }) =>
      apiClient.users.update(userId, data),
    onSuccess: (user) => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      setIsEditDialogOpen(false);
      setEditingUser(null);
      toast.success(`User "${user.username}" updated successfully`);
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to update user');
    },
  });

  // Delete user mutation
  const deleteUserMutation = useMutation({
    mutationFn: (userId: string) => apiClient.users.delete(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      toast.success('User deleted successfully');
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to delete user');
    },
  });

  // Reset password mutation
  const resetPasswordMutation = useMutation({
    mutationFn: (userId: string) => apiClient.users.resetPassword(userId),
    onSuccess: (response, userId) => {
      const user = users?.find(u => u.id === userId);
      toast.success(`Password reset for "${user?.username || 'user'}"`);
      setTemporaryPassword(response.temporary_password);
      setIsCreateDialogOpen(true); // Reuse dialog to show password
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to reset password');
    },
  });

  const handleCreateUser = () => {
    if (!newUsername.trim()) {
      toast.error('Username is required');
      return;
    }
    if (sendEmail && !newEmail.trim()) {
      toast.error('Email is required to send invitation');
      return;
    }
    createUserMutation.mutate({
      username: newUsername.trim(),
      email: newEmail.trim() || undefined,
      role: newRole,
      send_email: sendEmail && !!newEmail.trim(),
    });
  };

  const handleEditUser = (user: IUser) => {
    setEditingUser(user);
    setEditEmail(user.email || '');
    setEditRole(user.role);
    setEditIsActive(user.is_active);
    setIsEditDialogOpen(true);
  };

  const handleUpdateUser = () => {
    if (!editingUser) return;
    updateUserMutation.mutate({
      userId: editingUser.id,
      data: {
        email: editEmail.trim() || undefined,
        role: editRole,
        is_active: editIsActive,
      },
    });
  };

  const copyPassword = async () => {
    if (temporaryPassword) {
      await navigator.clipboard.writeText(temporaryPassword);
      setCopiedPassword(true);
      setTimeout(() => setCopiedPassword(false), 2000);
    }
  };

  const closeCreateDialog = () => {
    setIsCreateDialogOpen(false);
    setTemporaryPassword(null);
    setCopiedPassword(false);
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Never';
    return formatLocale(dateString);
  };

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5" />
            User Management
          </CardTitle>
          <CardDescription>
            Manage user accounts and permissions
          </CardDescription>
        </div>
        <Dialog open={isCreateDialogOpen} onOpenChange={(open) => {
          if (!open) closeCreateDialog();
          else setIsCreateDialogOpen(true);
        }}>
          <DialogTrigger asChild>
            <Button size="sm">
              <Plus className="h-4 w-4 mr-2" />
              Add User
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>
                {temporaryPassword ? 'User Created' : 'Create New User'}
              </DialogTitle>
              <DialogDescription>
                {temporaryPassword
                  ? 'Save this temporary password - it will not be shown again.'
                  : 'Create a new user account with a temporary password.'}
              </DialogDescription>
            </DialogHeader>
            {temporaryPassword ? (
              <div className="space-y-4">
                <div className="p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
                  <p className="text-sm text-yellow-600 dark:text-yellow-400 font-medium mb-2">
                    Temporary Password
                  </p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 p-2 bg-muted rounded font-mono text-sm">
                      {temporaryPassword}
                    </code>
                    <Button variant="outline" size="icon" onClick={copyPassword}>
                      {copiedPassword ? (
                        <Check className="h-4 w-4 text-green-500" />
                      ) : (
                        <Copy className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">
                    This password expires in 72 hours. User must change it on first login.
                  </p>
                </div>
                <DialogFooter>
                  <Button onClick={closeCreateDialog}>Done</Button>
                </DialogFooter>
              </div>
            ) : (
              <>
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="username">Username</Label>
                    <Input
                      id="username"
                      placeholder="Enter username"
                      value={newUsername}
                      onChange={(e) => setNewUsername(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="email">Email (optional)</Label>
                    <Input
                      id="email"
                      type="email"
                      placeholder="Enter email"
                      value={newEmail}
                      onChange={(e) => setNewEmail(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="role">Role</Label>
                    <Select value={newRole} onValueChange={(v) => setNewRole(v as UserRole)}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="admin">
                          <div className="flex items-center gap-2">
                            <Shield className="h-4 w-4" />
                            Admin
                          </div>
                        </SelectItem>
                        <SelectItem value="operator">
                          <div className="flex items-center gap-2">
                            <UserCog className="h-4 w-4" />
                            Operator
                          </div>
                        </SelectItem>
                        <SelectItem value="viewer">
                          <div className="flex items-center gap-2">
                            <Eye className="h-4 w-4" />
                            Viewer
                          </div>
                        </SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      {roleDescriptions[newRole]}
                    </p>
                  </div>
                  {/* Story P16-1.7: Send invitation email option */}
                  {smtpSettings?.enabled && (
                    <div className="flex items-center justify-between rounded-lg border p-3">
                      <div className="flex items-center gap-2">
                        <Mail className="h-4 w-4 text-muted-foreground" />
                        <div className="space-y-0.5">
                          <Label htmlFor="send-email" className="cursor-pointer">
                            Send Invitation Email
                          </Label>
                          <p className="text-xs text-muted-foreground">
                            Email credentials to the user (requires email)
                          </p>
                        </div>
                      </div>
                      <Switch
                        id="send-email"
                        checked={sendEmail}
                        onCheckedChange={setSendEmail}
                        disabled={!newEmail.trim()}
                      />
                    </div>
                  )}
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setIsCreateDialogOpen(false)}>
                    Cancel
                  </Button>
                  <Button
                    onClick={handleCreateUser}
                    disabled={createUserMutation.isPending}
                  >
                    {createUserMutation.isPending && (
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    )}
                    Create User
                  </Button>
                </DialogFooter>
              </>
            )}
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent>
        <TooltipProvider>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Username</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last Login</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users?.map((user) => {
                const RoleIcon = roleIcons[user.role];
                const isCurrentUser = user.id === currentUserId;
                return (
                  <TableRow key={user.id}>
                    <TableCell className="font-medium">
                      {user.username}
                      {isCurrentUser && (
                        <Badge variant="outline" className="ml-2 text-xs">
                          You
                        </Badge>
                      )}
                      {user.must_change_password && (
                        <Badge variant="secondary" className="ml-2 text-xs">
                          Password Change Required
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {user.email || '-'}
                    </TableCell>
                    <TableCell>
                      <Tooltip>
                        <TooltipTrigger>
                          <Badge className={roleColors[user.role]}>
                            <RoleIcon className="h-3 w-3 mr-1" />
                            {user.role.charAt(0).toUpperCase() + user.role.slice(1)}
                          </Badge>
                        </TooltipTrigger>
                        <TooltipContent>
                          {roleDescriptions[user.role]}
                        </TooltipContent>
                      </Tooltip>
                    </TableCell>
                    <TableCell>
                      {user.is_active ? (
                        <Badge variant="outline" className="text-green-500 border-green-500/20 bg-green-500/10">
                          <Check className="h-3 w-3 mr-1" />
                          Active
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-red-500 border-red-500/20 bg-red-500/10">
                          <X className="h-3 w-3 mr-1" />
                          Inactive
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {formatDate(user.last_login)}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleEditUser(user)}
                              disabled={isCurrentUser}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>
                            {isCurrentUser ? 'Cannot edit yourself' : 'Edit user'}
                          </TooltipContent>
                        </Tooltip>

                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => resetPasswordMutation.mutate(user.id)}
                              disabled={resetPasswordMutation.isPending}
                            >
                              <Key className="h-4 w-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Reset password</TooltipContent>
                        </Tooltip>

                        <AlertDialog>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <AlertDialogTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="text-destructive hover:text-destructive"
                                  disabled={isCurrentUser}
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </AlertDialogTrigger>
                            </TooltipTrigger>
                            <TooltipContent>
                              {isCurrentUser ? 'Cannot delete yourself' : 'Delete user'}
                            </TooltipContent>
                          </Tooltip>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>Delete User</AlertDialogTitle>
                              <AlertDialogDescription>
                                Are you sure you want to delete &quot;{user.username}&quot;?
                                This action cannot be undone.
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>Cancel</AlertDialogCancel>
                              <AlertDialogAction
                                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                                onClick={() => deleteUserMutation.mutate(user.id)}
                              >
                                Delete
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
              {(!users || users.length === 0) && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                    No users found
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TooltipProvider>
      </CardContent>

      {/* Edit User Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit User</DialogTitle>
            <DialogDescription>
              Update user details for &quot;{editingUser?.username}&quot;
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="edit-email">Email</Label>
              <Input
                id="edit-email"
                type="email"
                placeholder="Enter email"
                value={editEmail}
                onChange={(e) => setEditEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-role">Role</Label>
              <Select value={editRole} onValueChange={(v) => setEditRole(v as UserRole)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="admin">
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4" />
                      Admin
                    </div>
                  </SelectItem>
                  <SelectItem value="operator">
                    <div className="flex items-center gap-2">
                      <UserCog className="h-4 w-4" />
                      Operator
                    </div>
                  </SelectItem>
                  <SelectItem value="viewer">
                    <div className="flex items-center gap-2">
                      <Eye className="h-4 w-4" />
                      Viewer
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {roleDescriptions[editRole]}
              </p>
            </div>
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label>Account Status</Label>
                <p className="text-xs text-muted-foreground">
                  Inactive users cannot log in
                </p>
              </div>
              <Switch
                checked={editIsActive}
                onCheckedChange={setEditIsActive}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleUpdateUser}
              disabled={updateUserMutation.isPending}
            >
              {updateUserMutation.isPending && (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              )}
              Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
