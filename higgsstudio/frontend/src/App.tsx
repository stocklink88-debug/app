import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { Spinner, ToastHost } from './components/ui'
import { SessionProvider, useSession } from './lib/session'
import Ads from './pages/Ads'
import Auth from './pages/Auth'
import Billing from './pages/Billing'
import Characters from './pages/Characters'
import Create from './pages/Create'
import Effects from './pages/Effects'
import Explore from './pages/Explore'
import Jobs from './pages/Jobs'
import Library from './pages/Library'
import Projects, { ProjectDetail } from './pages/Projects'
import Settings from './pages/Settings'
import Tools from './pages/Tools'
import Voices from './pages/Voices'

function Shell() {
  const { user, loading } = useSession()

  if (loading) {
    return (
      <div className="min-h-screen grid place-items-center">
        <div className="text-center">
          <span className="w-12 h-12 rounded-2xl bg-brand grid place-items-center
                           text-ink-950 font-black text-xl mx-auto mb-4">H</span>
          <Spinner className="w-5 h-5 mx-auto text-zinc-600" />
        </div>
      </div>
    )
  }

  if (!user) return <Auth />

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Explore />} />
        <Route path="/crear" element={<Create />} />
        <Route path="/efectos" element={<Effects />} />
        <Route path="/herramientas" element={<Tools />} />
        <Route path="/biblioteca" element={<Library />} />
        <Route path="/proyectos" element={<Projects />} />
        <Route path="/proyectos/:id" element={<ProjectDetail />} />
        <Route path="/personajes" element={<Characters />} />
        <Route path="/anuncios" element={<Ads />} />
        <Route path="/voces" element={<Voices />} />
        <Route path="/trabajos" element={<Jobs />} />
        <Route path="/creditos" element={<Billing />} />
        <Route path="/ajustes" element={<Settings />} />
        <Route path="*" element={<Explore />} />
      </Routes>
    </Layout>
  )
}

export default function App() {
  return (
    <ToastHost>
      <SessionProvider>
        <Shell />
      </SessionProvider>
    </ToastHost>
  )
}
