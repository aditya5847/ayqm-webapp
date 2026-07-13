import { Navigate, Route, Routes } from "react-router-dom";
import { AdminEpisodesPage, AdminGate, AdminLoginPage, AdminTriviaSearchPage, RssImportPage, SpeakersPage, SundayQuizAdminPage, UploadPage } from "./admin";
import {
  EpisodeDetailsTab, EpisodeOverviewTab, EpisodeSpeakerMappingTab,
  EpisodeTranscriptTab, EpisodeTriviaTab, EpisodeWorkspaceLayout
} from "./episode-admin";
import { AboutPage, HomePage, PublicEpisodePage, PublicEpisodesPage, PublicLayout, PublicSundayQuizArchivePage, PublicSundayQuizPlayPage, PublicTriviaPage } from "./public";

function App() {
  return (
    <Routes>
      <Route element={<PublicLayout />}>
        <Route index element={<HomePage />} />
        <Route path="episodes" element={<PublicEpisodesPage />} />
        <Route path="episodes/:episodeId" element={<PublicEpisodePage />} />
        <Route path="trivia" element={<PublicTriviaPage />} />
        <Route path="sunday-quiz" element={<PublicSundayQuizArchivePage />} />
        <Route path="sunday-quiz/:quizId" element={<PublicSundayQuizPlayPage />} />
        <Route path="about" element={<AboutPage />} />
      </Route>
      <Route path="admin/login" element={<AdminLoginPage />} />
      <Route path="admin" element={<AdminGate />}>
        <Route index element={<Navigate to="episodes" replace />} />
        <Route path="episodes" element={<AdminEpisodesPage />} />
        <Route path="trivia" element={<AdminTriviaSearchPage />} />
        <Route path="sunday-quizzes" element={<SundayQuizAdminPage />} />
        <Route path="episodes/new" element={<UploadPage />} />
        <Route path="imports" element={<RssImportPage />} />
        <Route path="episodes/:episodeId" element={<EpisodeWorkspaceLayout />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<EpisodeOverviewTab />} />
          <Route path="details" element={<EpisodeDetailsTab />} />
          <Route path="speaker-mapping" element={<EpisodeSpeakerMappingTab />} />
          <Route path="transcript" element={<EpisodeTranscriptTab />} />
          <Route path="trivia" element={<EpisodeTriviaTab />} />
        </Route>
        <Route path="speakers" element={<SpeakersPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
