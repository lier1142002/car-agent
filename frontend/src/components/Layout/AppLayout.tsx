import React, { useState } from 'react';
import { Layout } from 'antd';
import { Sidebar } from '../Sidebar/Sidebar';
import { ChatPanel } from '../Chat/ChatPanel';
import { TracePanel } from '../Trace/TracePanel';
import { SettingsDrawer } from '../Settings/SettingsDrawer';
import { EvalPanel } from '../Settings/EvalPanel';

const { Sider, Content } = Layout;

export const AppLayout: React.FC = () => {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [evalOpen, setEvalOpen] = useState(false);

  return (
    <Layout style={{ height: '100vh' }}>
      <Sider width={220} style={{ background: '#0d1117', borderRight: '1px solid #30363d' }}>
        <Sidebar
          onOpenSettings={() => setSettingsOpen(true)}
          onOpenEval={() => setEvalOpen(true)}
        />
      </Sider>
      <Content style={{ display: 'flex', flexDirection: 'column' }}>
        <ChatPanel />
      </Content>
      <Sider width={300} style={{ background: '#0d1117', borderLeft: '1px solid #30363d' }}>
        <TracePanel />
      </Sider>
      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <EvalPanel open={evalOpen} onClose={() => setEvalOpen(false)} />
    </Layout>
  );
};
