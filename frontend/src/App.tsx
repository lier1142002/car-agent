import React from 'react';
import { ConfigProvider, theme, App as AntApp } from 'antd';
import { AppProvider } from './store/AppContext';
import { ChatPage } from './pages/ChatPage';

const App: React.FC = () => {
  return (
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#58a6ff',
          colorBgContainer: '#161b22',
          colorBgElevated: '#1c2333',
          colorBorder: '#30363d',
          colorText: '#e6edf3',
          colorTextSecondary: '#8b949e',
          borderRadius: 8,
        },
      }}
    >
      <AntApp>
        <AppProvider>
          <ChatPage />
        </AppProvider>
      </AntApp>
    </ConfigProvider>
  );
};

export default App;
