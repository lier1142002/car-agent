import React from 'react';
import { Drawer, Tabs, Button, Typography, Divider, message } from 'antd';
import { LogoutOutlined, UserOutlined, SettingOutlined } from '@ant-design/icons';
import { PdfUploader } from './PdfUploader';
import { uploadPdf } from '../../services/api';
import { useApp } from '../../store/AppContext';
import styles from '../../styles/Settings.module.css';

interface Props {
  open: boolean;
  onClose: () => void;
  username: string;
  onLogout: () => void;
}

export const SettingsDrawer: React.FC<Props> = ({ open, onClose, username, onLogout }) => {
  const { refreshAgentState } = useApp();

  const handlePdfUpload = async (file: File) => {
    try {
      const result = await uploadPdf(file);
      if (result.status === 'success') {
        message.success(`已切分为 ${result.chunks} 块，成功入库`);
        refreshAgentState();
      } else {
        message.error(result.message || '上传失败');
      }
    } catch {
      message.error('上传失败');
    }
  };

  return (
    <Drawer
      title={<><SettingOutlined /> 设置</>}
      placement="right"
      width={420}
      open={open}
      onClose={onClose}
      className={styles.drawer}
    >
      <Tabs
        items={[
          {
            key: 'account',
            label: <span><UserOutlined /> 账户</span>,
            children: (
              <div>
                <Typography.Title level={5}>当前用户: {username}</Typography.Title>
                <Typography.Paragraph type="secondary">
                  API Key 配置已迁移到环境变量 (.env)。每位用户可在 Redis 中存储自己的 API Key。
                </Typography.Paragraph>
                <Divider />
                <Button icon={<LogoutOutlined />} danger block onClick={onLogout}>
                  退出登录
                </Button>
              </div>
            ),
          },
          {
            key: 'knowledge',
            label: '📄 知识库',
            children: <PdfUploader onUpload={handlePdfUpload} />,
          },
        ]}
      />
    </Drawer>
  );
};
