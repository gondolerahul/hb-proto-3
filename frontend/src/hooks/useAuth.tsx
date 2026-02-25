import React, { createContext, useContext, useState, useEffect } from 'react';
import { User } from '@/types';
import { authService } from '@/services/auth.service';

interface AuthContextType {
    user: User | null;
    token: string | null;
    loading: boolean;
    login: (email: string, password: string) => Promise<void>;
    register: (email: string, password: string, fullName: string) => Promise<void>;
    logout: () => void;
    isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [user, setUser] = useState<User | null>(null);
    const [token, setToken] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const initAuth = async () => {
            const storedToken = authService.isAuthenticated() ? localStorage.getItem('access_token') : null;
            setToken(storedToken);

            if (storedToken) {
                try {
                    const currentUser = await authService.getCurrentUser();
                    setUser(currentUser);
                } catch (error) {
                    console.error('Failed to fetch current user:', error);
                    authService.logout();
                    setToken(null);
                }
            }
            setLoading(false);
        };

        initAuth();
    }, []);

    const login = async (email: string, password: string) => {
        const response = await authService.login({ email, password });
        setUser(response.user);
        setToken(localStorage.getItem('access_token'));
        window.location.href = '/dashboard';
    };

    const register = async (email: string, password: string, fullName: string) => {
        const response = await authService.register({
            email,
            password,
            full_name: fullName,
        });
        setUser(response.user);
        setToken(localStorage.getItem('access_token'));
        window.location.href = '/dashboard';
    };

    const logout = () => {
        authService.logout();
        setUser(null);
        setToken(null);
    };

    return (
        <AuthContext.Provider
            value={{
                user,
                token,
                loading,
                login,
                register,
                logout,
                isAuthenticated: !!user,
            }}
        >
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = (): AuthContextType => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};
