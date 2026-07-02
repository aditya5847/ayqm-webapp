import { Navigate, Route, Routes } from "react-router-dom";
import { AdminEpisodePage, AdminEpisodesPage, AdminGate, AdminLoginPage, SpeakersPage, UploadPage } from "./admin";
import { AboutPage, HomePage, PublicEpisodePage, PublicEpisodesPage, PublicLayout, PublicTriviaPage } from "./public";

function App() {
  return (
    <Routes>
      <Route element={<PublicLayout />}>
        <Route index element={<HomePage />} />
        <Route path="episodes" element={<PublicEpisodesPage />} />
        <Route path="episodes/:episodeId" element={<PublicEpisodePage />} />
        <Route path="trivia" element={<PublicTriviaPage />} />
        <Route path="about" element={<AboutPage />} />
      </Route>
      <Route path="admin/login" element={<AdminLoginPage />} />
      <Route path="admin" element={<AdminGate />}>
        <Route index element={<Navigate to="episodes" replace />} />
        <Route path="episodes" element={<AdminEpisodesPage />} />
        <Route path="episodes/new" element={<UploadPage />} />
        <Route path="episodes/:episodeId" element={<AdminEpisodePage />} />
        <Route path="speakers" element={<SpeakersPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
