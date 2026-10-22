import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { LeadLayout, PublicLayout } from './components/Layout'
import QueuePage from './pages/Queue'
import ApplicantsPage from './pages/Applicants'
import ApplicantPage from './pages/Applicant'
import BlocklistPage from './pages/Blocklist'
import SettingsPage from './pages/Settings'
import EvalPage from './pages/Evaluation'
import ApplyPage from './pages/Apply'
import AppealPage from './pages/Appeal'
import MessageCheckPage from './pages/MessageCheck'

export const DEFAULT_SLUG = 'grok-night-london'
const lastSlug = () => localStorage.getItem('gk.community') ?? DEFAULT_SLUG

function CommunityRedirect() {
  const { slug } = useParams()
  return <Navigate to={`/c/${slug}/queue`} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to={`/c/${lastSlug()}/queue`} replace />} />
      <Route element={<PublicLayout />}>
        <Route path="/apply/:slug" element={<ApplyPage />} />
        <Route path="/appeal" element={<AppealPage />} />
      </Route>
      <Route path="/c/:slug" element={<LeadLayout />}>
        <Route index element={<CommunityRedirect />} />
        <Route path="queue" element={<QueuePage />} />
        <Route path="applicants" element={<ApplicantsPage />} />
        <Route path="applicants/:id" element={<ApplicantPage />} />
        <Route path="blocklist" element={<BlocklistPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="eval" element={<EvalPage />} />
        <Route path="moderation" element={<MessageCheckPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
