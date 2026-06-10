import { Layout, Menu } from 'antd'
import { ExperimentOutlined, ApartmentOutlined } from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'

const { Header, Sider, Content } = Layout

function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()

  const menuItems = [
    { key: '/experiments', icon: <ExperimentOutlined />, label: '实验管理' },
    { key: '/layers', icon: <ApartmentOutlined />, label: '流量层' },
  ]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider>
        <div style={{ height: 32, margin: 16, color: '#fff', fontSize: 18, fontWeight: 'bold', textAlign: 'center' }}>
          SplitLab
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname.startsWith('/layers') ? '/layers' : '/experiments']}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', fontSize: 16 }}>
          A/B 实验平台
        </Header>
        <Content style={{ margin: 24, padding: 24, background: '#fff', borderRadius: 8 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}

export default AppLayout
