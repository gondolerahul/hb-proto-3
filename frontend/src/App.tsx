import React from 'react';
import { AuthProvider } from './hooks/useAuth';
import { ThemeProvider } from './hooks/useTheme';
import { AppRouter } from './router';
import './styles/tokens.css';
import './styles/theme.css';
import './styles/global.css';

const App: React.FC = () => {
    return (
        <ThemeProvider>
            <AuthProvider>
                <AppRouter />
            </AuthProvider>
        </ThemeProvider>
    );
};

export default App;
