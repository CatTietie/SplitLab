import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import Dashboard from './pages/Dashboard'
import ExperimentPage from './pages/ExperimentPage'
import LayerPage from './pages/LayerPage'
import AppLayout from './components/AppLayout'

function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<AppLayout />}>
            <Route index element={<Navigate to="/experiments" replace />} />
            <Route path="experiments" element={<Dashboard />} />
            <Route path="experiments/:id" element={<ExperimentPage />} />
            <Route path="layers" element={<LayerPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}

export default App
