import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './index.css'
import Login from './pages/Login.jsx'
import Operator from './pages/Operator.jsx'
import Admin from './pages/Admin.jsx'
import { getUser } from './api.js'

function Guard({ role, children }) {
  const u = getUser()
  if (!u) return <Navigate to="/login" replace />
  if (role && u.role !== role) return <Navigate to={u.role === 'admin' ? '/admin' : '/operator'} replace />
  return children
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/operator" element={<Guard role="operator"><Operator /></Guard>} />
        <Route path="/admin" element={<Guard role="admin"><Admin /></Guard>} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
