import React from 'react';
import { Layout } from 'antd';
import { Sidebar } from '../Sidebar/Sidebar';
import { ChatPanel } from '../Chat/ChatPanel';
import { TracePanel } from '../Trace/TracePanel';

const { Sider, Content } = Layout;

export const AppLayout: React.FC = () => {
  return (
    <Layout style={{ height: '100vh' }}>
      <Sider
        width={220}
        style={{
          background: 'var(--bg-sidebar)',
          borderRight: '1px solid var(--border-color)',
          overflow: 'hidden',
        }}
      >
        <Sidebar />
      </Sider>
      <Content style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <ChatPanel />
      </Content>
      <Sider
        width={300}
        style={{
          background: 'var(--bg-secondary)',
          borderLeft: '1px solid var(--border-color)',
          overflow: 'hidden',
        }}
      >
        <TracePanel />
      </Sider>
    </Layout>
  );
};
