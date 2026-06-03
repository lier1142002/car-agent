import React, { useState, useCallback } from 'react';
import { ConfigProvider, theme, App as AntApp } from 'antd';
import { AppProvider } from './store/AppContext';
import { AppLayout } from './components/Layout/AppLayout';
import { LoginPage } from './components/LoginPage';
import { isLoggedIn, clearToken } from './services/api';
import './styles/global.css';

const App: React.FC = () => {
  const [username, setUsername] = useState<string | null>(() => {
    return isLoggedIn() ? localStorage.getItem('agent_car_username') : null;
  });

  const handleLogin = useCallback((name: string) => {
    localStorage.setItem('agent_car_username', name);
    setUsername(name);
  }, []);

  const handleLogout = useCallback(() => {
    clearToken();
    localStorage.removeItem('agent_car_username');
    setUsername(null);
  }, []);

  if (!username) {
    return (
      <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>
        <LoginPage onLogin={handleLogin} />
      </ConfigProvider>
    );
  }

  return (
    <ConfigProvider theme={{ algorithm: theme.darkAlgorithm }}>
      <AntApp>
        <AppProvider>
          <AppLayout onLogout={handleLogout} username={username} />
        </AppProvider>
      </AntApp>
    </ConfigProvider>
  );
};

export default App;
