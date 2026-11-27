import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { EmptyState, Layout } from './components'
import { AlertDetail, AlertsList } from './pages/Alerts'
import ModelPerformance from './pages/ModelPerformance'
import Overview from './pages/Overview'
import Traffic from './pages/Traffic'

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/traffic" element={<Traffic />} />
          <Route path="/alerts" element={<AlertsList />} />
          <Route path="/alerts/:id" element={<AlertDetail />} />
          <Route path="/model" element={<ModelPerformance />} />
          <Route path="*" element={<EmptyState>Page not found.</EmptyState>} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
