import React, { useState } from 'react';
import { Card, Input, Button, Tabs, message, Space } from 'antd';
import { UserOutlined, LockOutlined, CarOutlined } from '@ant-design/icons';
import { login, register, setToken } from '../services/api';

interface Props {
  onLogin: (username: string) => void;
}

export const LoginPage: React.FC<Props> = ({ onLogin }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    if (!username.trim() || !password.trim()) return;
    setLoading(true);
    try {
      const resp = await login(username, password);
      setToken(resp.token);
      message.success(`欢迎回来, ${resp.username}!`);
      onLogin(resp.username);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '登录失败');
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async () => {
    if (!username.trim() || password.length < 6) {
      message.warning('密码至少6位');
      return;
    }
    setLoading(true);
    try {
      const resp = await register(username, password);
      setToken(resp.token);
      message.success(`注册成功! 欢迎, ${resp.username}!`);
      onLogin(resp.username);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '注册失败');
    } finally {
      setLoading(false);
    }
  };

  const tabItems = [
    {
      key: 'login',
      label: '登录',
      children: (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input prefix={<UserOutlined />} placeholder="用户名" value={username}
            onChange={e => setUsername(e.target.value)} onPressEnter={handleLogin} />
          <Input.Password prefix={<LockOutlined />} placeholder="密码" value={password}
            onChange={e => setPassword(e.target.value)} onPressEnter={handleLogin} />
          <Button type="primary" block loading={loading} onClick={handleLogin}>登录</Button>
        </Space>
      ),
    },
    {
      key: 'register',
      label: '注册',
      children: (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Input prefix={<UserOutlined />} placeholder="用户名 (3-32位)" value={username}
            onChange={e => setUsername(e.target.value)} onPressEnter={handleRegister} />
          <Input.Password prefix={<LockOutlined />} placeholder="密码 (6位以上)" value={password}
            onChange={e => setPassword(e.target.value)} onPressEnter={handleRegister} />
          <Button type="primary" block loading={loading} onClick={handleRegister}>注册</Button>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#141414' }}>
      <Card style={{ width: 400 }} title={<span><CarOutlined /> AutoSales Agent</span>}>
        <Tabs items={tabItems} />
      </Card>
    </div>
  );
};
