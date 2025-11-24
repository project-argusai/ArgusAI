/**
 * Authentication context for managing user auth state
 * Phase 1.5 feature - placeholder implementation for now
 */

'use client';

import { createContext, useContext, useState, useCallback, ReactNode } from 'react';

export interface User {
  id: string;
  username: string;
  email?: string;
}

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const login = useCallback(async (username: string, _password: string) => {
    setIsLoading(true);
    try {
      // Placeholder - actual implementation in Phase 1.5
      // Will call backend /api/v1/login endpoint
      console.log('Login called (Phase 1.5 feature):', username);

      // Simulated user object
      const mockUser: User = {
        id: 'user-1',
        username,
        email: `${username}@example.com`,
      };
      setUser(mockUser);
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    setIsLoading(true);
    try {
      // Placeholder - actual implementation in Phase 1.5
      // Will call backend /api/v1/logout endpoint
      console.log('Logout called (Phase 1.5 feature)');
      setUser(null);
    } catch (error) {
      console.error('Logout failed:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
