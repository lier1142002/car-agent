import React from 'react';
import { AppLayout } from '../components/Layout/AppLayout';

interface Props {
  onLogout: () => void;
  username: string;
}

export const ChatPage: React.FC<Props> = ({ onLogout, username }) => {
  return <AppLayout onLogout={onLogout} username={username} />;
};
