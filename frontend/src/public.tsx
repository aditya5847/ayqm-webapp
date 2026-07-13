import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import DOMPurify from "dompurify";
import { ArrowLeft, ArrowRight, CheckCircle2, ExternalLink, Facebook, Instagram, Mail, Menu, MessageCircle, RefreshCw, Search, Trophy, X, XCircle, Youtube } from "lucide-react";
import { Link, NavLink, Outlet, useParams, useSearchParams } from "react-router-dom";
import type { PublicEpisode, PublicSpeaker, PublicSundayQuizQuestion, PublicSundayQuizSummary, TriviaItem } from "./types";
import {
  apiAssetUrl, getPublicEpisode, getPublicEpisodeTrivia, getPublicSundayQuiz, listPublicEpisodePage,
  listPublicEpisodes, listPublicSpeakers, listPublicSundayQuizzes, listRandomPublicTrivia, searchRandomPublicTrivia,
  submitSundayQuizAttempt
} from "./api";
import { formatDate, formatDateOnly, triviaAskerName } from "./workflow";
import { ErrorMessage, Notice, QueryState } from "./ui";
import logoUrl from "../references/Logo.png";
import thumbnailUrl from "../references/Podcast Thumbnail.jpg";

export function PublicLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="public-shell">
      <header className="public-header">
        <Link className="public-brand" to="/" aria-label="Are You Quizzing Me home">
          <img src={logoUrl} alt="Are You Quizzing Me?" />
        </Link>
        <button className="menu-button" type="button" aria-label="Toggle navigation" aria-expanded={menuOpen} onClick={() => setMenuOpen((value) => !value)}>
          {menuOpen ? <X /> : <Menu />}
        </button>
        <nav className={`public-nav${menuOpen ? " open" : ""}`} aria-label="Main navigation" onClick={() => setMenuOpen(false)}>
          <NavLink to="/" end>Home</NavLink>
          <NavLink to="/episodes">Episodes</NavLink>
          <NavLink to="/trivia">Trivia</NavLink>
          <NavLink to="/sunday-quiz">Sunday Quiz</NavLink>
          <NavLink to="/about">About us</NavLink>
        </nav>
      </header>
      <main><Outlet /></main>
      <footer className="public-footer">
        <img src={logoUrl} alt="" />
        <p>Questions worth asking. Answers worth remembering.</p>
        <div className="footer-links"><Link to="/about">About us</Link></div>
      </footer>
    </div>
  );
}

export function HomePage() {
  const episodes = useQuery({ queryKey: ["public", "episodes"], queryFn: listPublicEpisodes });
  const latest = episodes.data?.[0];
  const latestDescription = latest?.episode_description ?? (import.meta.env.MODE === "development" ? demoHeroDescription : null);

  return (
    <>
      <section className="home-hero">
        <div className="hero-art"><HeroArtwork latest={latest} /></div>
        <div className="hero-copy">
          <p className="comic-kicker">The podcast that asks</p>
          <h1>Are You Quizzing Me?</h1>
          {latest ? (
            <>
              <p className="episode-label">Latest: {episodeLabel(latest)}</p>
              <div className="hero-latest-row">
                <div className="hero-latest-top">
                  <EpisodeArtwork episode={latest} alt={`${latest.episode_title} artwork`} className="hero-latest-artwork" />
                    <h2>{latest.episode_title}</h2>
                </div>
                <div className="hero-latest-body">
                  <EpisodeDescription value={latestDescription} compact />
                  <div className="hero-actions">
                    <Link className="button primary" to={`/episodes/${latest.id}`}>Explore episode <ArrowRight size={18} /></Link>
                    {latest.source_url && <a className="button light" href={latest.source_url} target="_blank" rel="noreferrer">Listen <ExternalLink size={17} /></a>}
                  </div>
                </div>
              </div>
            </>
          ) : !episodes.isLoading && !episodes.error ? (
            <p>New episodes and questions are on the way.</p>
          ) : null}
        </div>
      </section>
      <div className="public-content">
        <QueryState query={episodes} feature="The episode showcase" empty="No episodes are available yet.">
          {(items) => <EpisodeStrip episodes={items.slice(1, 4)} />}
        </QueryState>
      </div>
    </>
  );
}

export function PublicEpisodesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const pageParam = searchParams.get("page");
  const requestedPage = positivePage(pageParam);
  const episodes = useQuery({
    queryKey: ["public", "episodes", "archive", requestedPage],
    queryFn: () => listPublicEpisodePage(requestedPage),
    placeholderData: keepPreviousData
  });
  useEffect(() => {
    if (!episodes.isPlaceholderData && episodes.data && (episodes.data.page !== requestedPage || (episodes.data.page === 1 && pageParam !== null))) {
      setSearchParams(episodes.data.page > 1 ? { page: String(episodes.data.page) } : {}, { replace: true });
    }
  }, [episodes.data, episodes.isPlaceholderData, pageParam, requestedPage, setSearchParams]);
  return (
    <PublicPageHeader eyebrow="Listen and explore" title="Episodes" intro="Every conversation, every question, and the trivia that came out of it.">
      <QueryState query={episodes} feature="The episode archive" empty="No episodes are available yet.">
        {(result) => result.items.length ? <><div className="episode-archive">{result.items.map((episode) => <EpisodeRow key={episode.id} episode={episode} />)}</div><EpisodePagination page={result.page} totalPages={result.total_pages} setSearchParams={setSearchParams} /></> : <Notice>No episodes are available yet.</Notice>}
      </QueryState>
    </PublicPageHeader>
  );
}

export function PublicEpisodePage() {
  const { episodeId = "" } = useParams();
  const episode = useQuery({ queryKey: ["public", "episode", episodeId], queryFn: () => getPublicEpisode(episodeId), enabled: Boolean(episodeId) });
  const trivia = useQuery({ queryKey: ["public", "episode", episodeId, "trivia"], queryFn: () => getPublicEpisodeTrivia(episodeId), enabled: Boolean(episodeId) });
  return (
    <div className="public-content episode-detail-public">
      <QueryState query={episode} feature="This episode page">
        {(item) => (
          <>
            <header className="episode-masthead">
              <EpisodeArtwork episode={item} alt={`${item.episode_title} artwork`} />
              <div><p className="eyebrow">{episodeLabel(item)}</p><h1>{item.episode_title}</h1><p className="episode-date">{formatDate(item.published_at)}</p><EpisodeDescription value={item.episode_description} /><p className="speaker-line">With {item.speakers.map((speaker) => speaker.name).join(", ") || "the AYQM panel"}</p>{item.source_url && <a className="button primary" href={item.source_url} target="_blank" rel="noreferrer">Listen to episode <ExternalLink size={17} /></a>}</div>
            </header>
            <section className="editorial-section"><div className="section-title-row"><div><p className="eyebrow">Play along</p><h2>Trivia from this episode</h2></div></div><QueryState query={trivia} feature="Episode trivia" empty="No trivia is available for this episode.">{(items) => <TriviaGrid items={items} />}</QueryState></section>
          </>
        )}
      </QueryState>
    </div>
  );
}

export function PublicTriviaPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const query = (searchParams.get("q") ?? "").trim();
  const [draft, setDraft] = useState(query);
  const [round, setRound] = useState(0);
  const [excludeIds, setExcludeIds] = useState<string[]>([]);
  const trivia = useQuery({
    queryKey: ["public", "trivia", "random", query, round],
    queryFn: () => query ? searchRandomPublicTrivia(query, 4, excludeIds) : listRandomPublicTrivia(4, excludeIds),
    placeholderData: keepPreviousData
  });
  useEffect(() => {
    setDraft(query);
    setExcludeIds([]);
    setRound(0);
  }, [query]);
  const refresh = () => {
    setExcludeIds(trivia.data?.map(item => item.id) ?? []);
    setRound(value => value + 1);
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const next = draft.trim();
    setSearchParams(next ? { q: next } : {});
  };
  const clear = () => {
    setDraft("");
    setSearchParams({});
  };
  const refreshLabel = query ? "Deal four matching cards" : "Deal four new cards";
  return (
    <PublicPageHeader eyebrow="Question bank" title="Trivia" intro="Four questions, pulled at random, from the podcast. Make your guess, then reveal the answer.">
      <form className="public-trivia-search" onSubmit={submit}><input aria-label="Search trivia" placeholder="Search trivia" value={draft} onChange={event => setDraft(event.target.value)} /><button className="button primary" type="submit" disabled={!draft.trim()}><Search size={16} />Search</button>{query && <button className="button light" type="button" onClick={clear}>Clear</button>}</form>
      <QueryState query={trivia} feature="The public trivia collection" empty={query ? `No trivia matched "${query}".` : "No trivia is available yet."}>{(items) => <><TriviaGrid key={`${query}-${round}`} items={items} /><div className="trivia-refresh"><button className="button light" type="button" onClick={refresh} disabled={trivia.isFetching}><RefreshCw className={trivia.isFetching ? "spin" : undefined} size={17} />{refreshLabel}</button></div></>}</QueryState>
    </PublicPageHeader>
  );
}

export function PublicSundayQuizArchivePage() {
  const quizzes = useQuery({ queryKey: ["public", "sunday-quizzes"], queryFn: listPublicSundayQuizzes });
  return <PublicPageHeader eyebrow="Weekly challenge" title="The Sunday Quiz" intro="One theme, ten questions, four options each. Play the latest set or browse the archive.">
    <QueryState query={quizzes} feature="The Sunday Quiz archive" empty="No Sunday Quizzes are published yet.">
      {items => <div className="sunday-quiz-archive">{items.map(item => <SundayQuizArchiveTile key={item.id} item={item} />)}</div>}
    </QueryState>
  </PublicPageHeader>;
}

function SundayQuizArchiveTile({ item }: { item: PublicSundayQuizSummary }) {
  const cover = apiAssetUrl(item.cover_image_url);
  return <article className="sunday-quiz-tile">
    {cover ? <img src={cover} alt="" /> : <div className="sunday-quiz-placeholder"><Trophy /></div>}
    <div>
      <p className="eyebrow">{formatDateOnly(item.quiz_date)} · {item.question_count} questions</p>
      <h2><Link to={`/sunday-quiz/${item.id}`}>{item.theme}</Link></h2>
      <Link className="button primary" to={`/sunday-quiz/${item.id}`}>Play quiz <ArrowRight size={17} /></Link>
    </div>
  </article>;
}

export function PublicSundayQuizPlayPage() {
  const { quizId = "" } = useParams();
  const quiz = useQuery({ queryKey: ["public", "sunday-quiz", quizId], queryFn: () => getPublicSundayQuiz(quizId), enabled: Boolean(quizId) });
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const attempt = useMutation({ mutationFn: () => submitSundayQuizAttempt(quizId, answers) });
  const allAnswered = quiz.data ? quiz.data.questions.every(question => answers[question.id] !== undefined) : false;
  useEffect(() => {
    setAnswers({});
  }, [quizId]);

  return <div className="public-content sunday-quiz-play">
    <QueryState query={quiz} feature="The Sunday Quiz">
      {item => <>
        <header className="sunday-quiz-masthead">
          {apiAssetUrl(item.cover_image_url) ? <img src={apiAssetUrl(item.cover_image_url) ?? ""} alt="" /> : <div className="sunday-quiz-placeholder"><Trophy /></div>}
          <div><p className="eyebrow">{formatDateOnly(item.quiz_date)} · {item.question_count} questions</p><h1>{item.theme}</h1>{attempt.data ? <p className="sunday-score">You scored {attempt.data.score}/{attempt.data.total}</p> : null}</div>
        </header>
        <form className="sunday-question-stack" onSubmit={event => { event.preventDefault(); attempt.mutate(); }}>
          {item.questions.map(question => <PublicSundayQuizQuestionCard key={question.id} question={question} selected={answers[question.id]} disabled={Boolean(attempt.data)} onSelect={value => setAnswers(current => ({ ...current, [question.id]: value }))} review={attempt.data?.review.find(result => result.question_id === question.id)} />)}
          {!attempt.data && <div className="sunday-submit-row"><button className="button primary" type="submit" disabled={!allAnswered || attempt.isPending}><Trophy size={17} />Submit answers</button></div>}
          <ErrorMessage error={attempt.error} />
        </form>
      </>}
    </QueryState>
  </div>;
}

function PublicSundayQuizQuestionCard({
  question,
  selected,
  disabled,
  onSelect,
  review
}: {
  question: PublicSundayQuizQuestion;
  selected: string | undefined;
  disabled: boolean;
  onSelect: (value: string) => void;
  review?: { selected_option_id: string | null; correct_option_id: string; selected_option_text: string | null; correct_option_text: string; correct: boolean; explanation: string | null; answer_image_url: string | null };
}) {
  return <article className={`sunday-question-card${review ? (review.correct ? " correct" : " incorrect") : ""}`}>
    <div className="sunday-question-number">{String(question.position).padStart(2, "0")}</div>
    <div className="sunday-question-body">
      {apiAssetUrl(question.question_image_url) && <img className="sunday-question-image" src={apiAssetUrl(question.question_image_url) ?? ""} alt="" />}
      <h2>{question.question}</h2>
      <div className="sunday-answer-options">
        {question.options.map((option, index) => {
          const isCorrect = review?.correct_option_id === option.id;
          const isSelectedWrong = review && review.selected_option_id === option.id && !isCorrect;
          return <label key={index} className={isCorrect ? "is-correct" : isSelectedWrong ? "is-wrong" : selected === option.id ? "is-selected" : undefined}>
          <input type="radio" name={question.id} value={option.id} checked={selected === option.id} disabled={disabled} onChange={() => onSelect(option.id)} />
          <span>{String.fromCharCode(65 + index)}</span>
          <strong>{option.text}</strong>
        </label>;
        })}
      </div>
      {review && <div className="sunday-review">
        <p>{review.correct ? <CheckCircle2 size={18} /> : <XCircle size={18} />}{review.correct ? "Correct" : `Correct answer: ${review.correct_option_text}`}</p>
        {review.explanation && <p>{review.explanation}</p>}
        {apiAssetUrl(review.answer_image_url) && <img src={apiAssetUrl(review.answer_image_url) ?? ""} alt="" />}
      </div>}
    </div>
  </article>;
}

const hostNames = new Set([
  normalizeGuestHostName("Aditya"),
  normalizeGuestHostName("Aditya Kashyap"),
  normalizeGuestHostName("Vineeth"),
  normalizeGuestHostName("Vineeth Nair")
]);

const hostPortraitModules = import.meta.glob("../references/hosts/*", { eager: true, query: "?url", import: "default" }) as Record<string, string>;
const isDevelopmentMode = import.meta.env.MODE === "development";
const demoGuestEpisodes: PublicEpisode[] = [
  {
    id: "demo-episode-12",
    episode_title: "Demo guest appearance",
    episode_number: 12,
    episode_kind: "main",
    episode_description: null,
    published_at: "2026-01-01T00:00:00Z",
    source_url: null,
    artwork_url: null,
    speakers: [{ id: "speaker-garry-leavy", name: "Garry Leavy" }],
    trivia_count: 0
  },
  {
    id: "demo-episode-29",
    episode_title: "Another demo guest appearance",
    episode_number: 29,
    episode_kind: "main",
    episode_description: null,
    published_at: "2026-01-08T00:00:00Z",
    source_url: null,
    artwork_url: null,
    speakers: [{ id: "speaker-garry-leavy", name: "Garry Leavy" }],
    trivia_count: 0
  }
];

export function AboutPage() {
  const speakers = useQuery({ queryKey: ["public", "about", "speakers"], queryFn: listPublicSpeakers });
  const episodes = useQuery({ queryKey: ["public", "about", "guest-episodes"], queryFn: listPublicEpisodes });
  const guestEpisodeMap = useMemo(() => groupGuestEpisodes(episodes.data ?? []), [episodes.data]);
  const guestSpeakers = useMemo<PublicSpeaker[]>(() => {
    const items = speakers.data ?? [];
    return items
      .filter((speaker) => !hostNames.has(normalizeGuestHostName(speaker.name)))
      .sort((left, right) => left.name.localeCompare(right.name));
  }, [speakers.data]);
  const guestEpisodeMapWithDemo = useMemo(() => {
    if (!isDevelopmentMode) return guestEpisodeMap;
    const next = new Map(guestEpisodeMap);
    const demoKey = normalizeGuestHostName("Garry Leavy");
    const existing = next.get(demoKey) ?? [];
    if (existing.length < 2) {
      next.set(demoKey, [...existing, ...demoGuestEpisodes]);
    }
    return next;
  }, [guestEpisodeMap]);
  return (
    <div className="about-page">
      <section className="about-hero">
        <div className="about-hero-copy">
          <p className="eyebrow">About us</p>
          <h1>Two trivia lovers. Far too many cool facts.</h1>
          <p>A trivia podcast created and hosted by Vineeth Nair and Aditya Kashyap.</p>
        </div>
        <img src={thumbnailUrl} alt="Are You Quizzing Me podcast artwork" />
      </section>

      <div className="public-content about-content">
        <section className="about-story">
          <div><p className="eyebrow">The story so far</p><h2>A podcast born from the urge to share one more fact</h2></div>
          <div className="about-prose">
            <p>The official version is simple: two men loved trivia, their friends and families had heard enough of their cool facts, and so they made a podcast. The first episode arrived on 4 January 2023.</p>
            <p>Since then, AYQM has grown into a weekly English-language show with more than 140 numbered episodes, usually running for about an hour. Each conversation moves freely through history, science, cinema, sport, language, culture and the stranger corners of everyday life, with questions designed to make the route to an answer as enjoyable as the answer itself.</p>
            <p>The show crossed its 100-episode mark in 2025 and returned after a short break ready for the next hundred. What began as an audio podcast now also includes video episodes, shorter clips, bonus mini episodes and a community where listeners can trade questions and discuss answers.</p>
          </div>
        </section>

        <section className="hosts-section">
          <div className="section-title-row"><div><p className="eyebrow">Behind the questions</p><h2>Meet the hosts</h2></div></div>
          <div className="host-grid">
            <article className="host-profile vineeth">
              <div className="host-profile-header"><HostPortrait host="vineeth" name="Vineeth Nair" initials="VN" /><div><p className="eyebrow">Co-founder and host</p><h3>Vineeth Nair</h3></div></div>
              <p>Vineeth is a quizmaster, podcast co-founder and the voice behind more than 140 AYQM appearances. His public professional record also spans pathology and medical diagnostics, giving him a life outside the podcast that is every bit as detail-oriented.</p>
              <p>Alongside the main show, Vineeth has presented bonus mini episodes that dig into overlooked moments from Indian history. His interests on AYQM range across history, science, culture and the connections hiding between them.</p>
            </article>
            <article className="host-profile aditya">
              <div className="host-profile-header"><HostPortrait host="aditya" name="Aditya Kashyap" initials="AK" /><div><p className="eyebrow">Co-founder and host</p><h3>Aditya Kashyap</h3></div></div>
              <p>Aditya is a quizmaster, seasoned host, actor and improv performer. He regularly conducts quizzes in Mumbai, has performed at comedy festivals across Asia, and has worked as an emcee for corporate events and educational institutions.</p>
              <p>He also teaches public speaking as a visiting faculty member and guest lecturer. On AYQM, that mix of quizzing, performance, improvisation and curiosity helps turn a collection of facts into a conversation.</p>
            </article>
          </div>
        </section>

        <section className="guest-section">
          <div><p className="eyebrow">Friends of the show</p><h2>Guest hosts so far</h2><p>Quizmasters and curious minds who have joined us behind the microphone.</p></div>
          <ol className="guest-list">
            {guestSpeakers.map((speaker, index) => {
              const episodes = guestEpisodeMapWithDemo.get(normalizeGuestHostName(speaker.name)) ?? [];
              const numberedEpisodes = episodes.filter((episode) => episode.episode_number != null);
              return (
                <li key={speaker.id}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div className="guest-list-copy">
                    <strong>{speaker.name}</strong>
                    <div className="guest-episodes">
                      {numberedEpisodes.length > 0 ? (
                        numberedEpisodes.map((episode) => (
                          <Link key={episode.id} to={`/episodes/${episode.id}`}>{episodeNumberBadge(episode)}</Link>
                        ))
                      ) : (
                        <p>No published episodes yet.</p>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        </section>

        <section className="connect-section">
          <div><p className="eyebrow">Keep quizzing</p><h2>Listen, watch and join in</h2></div>
          <div className="connect-links">
            <a href="https://open.spotify.com/show/21sPeqQbWmyaGQlWtjUbEA" target="_blank" rel="noreferrer"><ExternalLink />Spotify</a>
            <a href="https://podcasts.apple.com/in/podcast/are-you-quizzing-me/id1663104901" target="_blank" rel="noreferrer"><ExternalLink />Apple Podcasts</a>
            <a href="https://www.youtube.com/@areyouquizzingme/podcasts" target="_blank" rel="noreferrer"><Youtube />YouTube</a>
            <a href="https://www.instagram.com/areyouquizzingme/" target="_blank" rel="noreferrer"><Instagram />Instagram</a>
            <a href="https://www.reddit.com/r/areyouquizzingme/" target="_blank" rel="noreferrer"><MessageCircle />Reddit</a>
            <a href="https://www.facebook.com/areyouquizzingme" target="_blank" rel="noreferrer"><Facebook />Facebook</a>
            <a href="mailto:areyouquizzingme@gmail.com"><Mail />Email us</a>
          </div>
        </section>

        <aside className="about-sources" aria-label="About page sources">
          <p className="eyebrow">Research notes</p>
          <p>Show and host information was checked against the podcast's public listings and published event records in July 2026.</p>
          <div>
            <a href="https://podcasts.apple.com/in/podcast/are-you-quizzing-me/id1663104901" target="_blank" rel="noreferrer">Apple Podcasts <ExternalLink /></a>
            <a href="https://www.podchaser.com/podcasts/are-you-quizzing-me-5072758" target="_blank" rel="noreferrer">Podchaser <ExternalLink /></a>
            <a href="https://www.ncpamumbai.com/wp-content/uploads/2025/12/ON-Stage-April-2026-final.pdf" target="_blank" rel="noreferrer">NCPA host profile <ExternalLink /></a>
            <a href="https://www.goa.gov.in/wp-content/uploads/2019/12/SEMINAR-ON-CURRENT-TRENDS-IN-IDENTIFICATION-AN-DIAGNOSTICS-AT-KHANDOLA-.pdf" target="_blank" rel="noreferrer">Government of Goa record <ExternalLink /></a>
            <a href="https://www.reddit.com/r/india/comments/1pxs0j7/sharing_a_longrunning_indian_quizzing_podcast/" target="_blank" rel="noreferrer">Host introduction <ExternalLink /></a>
          </div>
        </aside>
      </div>
    </div>
  );
}

function PublicPageHeader({ eyebrow, title, intro, children }: { eyebrow: string; title: string; intro: string; children: React.ReactNode }) {
  return <div className="public-content"><header className="public-page-title"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{intro}</p></header>{children}</div>;
}

function EpisodeStrip({ episodes }: { episodes: PublicEpisode[] }) {
  return <section className="editorial-section"><div className="section-title-row"><div><p className="eyebrow">From the archive</p><h2>Recent episodes</h2></div><Link to="/episodes">All episodes <ArrowRight size={16} /></Link></div><div className="episode-strip">{episodes.map((episode) => <EpisodeTile key={episode.id} episode={episode} />)}</div></section>;
}

function EpisodeTile({ episode }: { episode: PublicEpisode }) {
  return <article className="episode-tile"><Link to={`/episodes/${episode.id}`}><EpisodeArtwork episode={episode} alt="" /><span>{episodeLabel(episode)}</span><h3>{episode.episode_title}</h3><EpisodeDescription value={episode.episode_description} compact className="clamp" /></Link></article>;
}

function EpisodeRow({ episode }: { episode: PublicEpisode }) {
  return <article className="episode-row"><EpisodeArtwork episode={episode} alt="" /><div><p className="eyebrow">{episodeLabel(episode)} · {formatDate(episode.published_at)}</p><h2><Link to={`/episodes/${episode.id}`}>{episode.episode_title}</Link></h2><EpisodeDescription value={episode.episode_description} compact /><span>{episode.trivia_count} trivia questions</span></div><Link className="icon-link" to={`/episodes/${episode.id}`} aria-label={`Open ${episode.episode_title}`}><ArrowRight /></Link></article>;
}

function HeroArtwork({ latest }: { latest?: PublicEpisode }) {
  return <img className="hero-podcast-cover" src={thumbnailUrl} alt="Are You Quizzing Me podcast artwork" />;
}

const demoHeroDescription = [
  "This is dummy hero copy for layout checking.",
  "It is intentionally long enough to wrap across several lines.",
  "That makes it easier to see whether the artwork, title, description, and buttons are balanced.",
  "Remove this once you are happy with the spacing."
].join(" ");

function EpisodeArtwork({ episode, alt, className = "" }: { episode?: PublicEpisode; alt: string; className?: string }) {
  const artwork = apiAssetUrl(episode?.artwork_url ?? null);
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [artwork]);
  return <img className={className || undefined} src={!failed && artwork ? artwork : thumbnailUrl} alt={alt} onError={() => setFailed(true)} />;
}

function EpisodeDescription({ value, compact = false, className = "" }: { value: string | null; compact?: boolean; className?: string }) {
  if (!value) return null;
  const cleaned = stripEpisodeContactFooter(value);
  const html = compact
    ? DOMPurify.sanitize(cleaned, { ALLOWED_TAGS: [], ALLOWED_ATTR: [] })
    : DOMPurify.sanitize(cleaned, {
      ALLOWED_TAGS: ["p", "br", "strong", "b", "em", "i", "ul", "ol", "li", "a", "blockquote"],
      ALLOWED_ATTR: ["href", "title"],
      ALLOW_DATA_ATTR: false
    });
  const classes = ["episode-description", compact ? "compact" : "rich", className].filter(Boolean).join(" ");
  const Element = compact ? "p" : "div";
  return <Element className={classes} dangerouslySetInnerHTML={{ __html: html }} />;
}

function stripEpisodeContactFooter(value: string): string {
  const marker = "you can reach us at";
  const root = new DOMParser().parseFromString(`<div id="episode-description-root">${value}</div>`, "text/html").getElementById("episode-description-root");
  if (!root) return value;

  const blockElements = Array.from(root.querySelectorAll("p, div, section, blockquote, li"));
  const footerBlock = blockElements.find((element) => {
    const text = element.textContent?.replace(/\s+/g, " ").trim().toLowerCase() ?? "";
    return text.includes(marker);
  });

  if (footerBlock) {
    let sibling: ChildNode | null = footerBlock;
    while (sibling) {
      const next: ChildNode | null = sibling.nextSibling;
      sibling.remove();
      sibling = next;
    }
    return root.innerHTML;
  }

  const text = root.textContent ?? "";
  const markerIndex = text.toLowerCase().indexOf(marker);
  if (markerIndex === -1) return root.innerHTML;

  root.innerHTML = text.slice(0, markerIndex).trimEnd();
  return root.innerHTML;
}

function HostPortrait({ host, name, initials }: { host: string; name: string; initials: string }) {
  const portrait = Object.entries(hostPortraitModules).find(([path]) => path.toLowerCase().includes(host))?.[1];
  return portrait
    ? <img className="host-portrait" src={portrait} alt={name} />
    : <div className="host-initials" aria-hidden="true">{initials}</div>;
}

function positivePage(value: string | null): number {
  const page = Number(value);
  return Number.isInteger(page) && page > 0 ? page : 1;
}

function EpisodePagination({ page, totalPages, setSearchParams }: { page: number; totalPages: number; setSearchParams: ReturnType<typeof useSearchParams>[1] }) {
  if (totalPages <= 1) return null;
  const pages = paginationPages(page, totalPages);
  const goToPage = (nextPage: number) => setSearchParams(nextPage > 1 ? { page: String(nextPage) } : {});
  return <nav className="pagination" aria-label="Episode pages">
    {page > 1 && <button type="button" onClick={() => goToPage(page - 1)}><ArrowLeft size={16} />Previous</button>}
    <div className="pagination-pages">{pages.map((item, index) => item === "ellipsis" ? <span key={`ellipsis-${index}`} aria-hidden="true">…</span> : <button key={item} type="button" aria-current={item === page ? "page" : undefined} onClick={() => goToPage(item)}>{item}</button>)}</div>
    {page < totalPages && <button type="button" onClick={() => goToPage(page + 1)}>Next<ArrowRight size={16} /></button>}
  </nav>;
}

function paginationPages(page: number, totalPages: number): Array<number | "ellipsis"> {
  const visible = new Set([1, totalPages, page - 1, page, page + 1].filter(item => item >= 1 && item <= totalPages));
  const ordered = [...visible].sort((a, b) => a - b);
  return ordered.flatMap((item, index) => index > 0 && item - ordered[index - 1] > 1 ? ["ellipsis", item] : [item]);
}

function episodeLabel(episode: PublicEpisode): string {
  if (episode.episode_kind === "announcement") return "Announcement";
  if (episode.episode_kind === "mini") return `Mini episode ${episode.episode_number}`;
  return `Episode ${episode.episode_number}`;
}

function normalizeGuestHostName(name: string): string {
  return name.trim().toLowerCase().replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ");
}

function episodeNumberBadge(episode: PublicEpisode): string | null {
  if (episode.episode_number == null) return null;
  return `#${episode.episode_number}`;
}

function groupGuestEpisodes(episodes: PublicEpisode[]): Map<string, PublicEpisode[]> {
  const grouped = new Map<string, PublicEpisode[]>();
  episodes.forEach((episode) => {
    episode.speakers.forEach((speaker) => {
      const key = normalizeGuestHostName(speaker.name);
      const current = grouped.get(key) ?? [];
      if (current.some((item) => item.id === episode.id)) return;
      current.push(episode);
      grouped.set(key, current);
    });
  });
  grouped.forEach((items, key) => {
    items.sort((left, right) => {
      const leftNumber = left.episode_number ?? Number.POSITIVE_INFINITY;
      const rightNumber = right.episode_number ?? Number.POSITIVE_INFINITY;
      if (leftNumber !== rightNumber) return leftNumber - rightNumber;
      return (right.published_at ?? "").localeCompare(left.published_at ?? "");
    });
    grouped.set(key, items);
  });
  return grouped;
}

export function TriviaGrid({ items }: { items: TriviaItem[] }) {
  return <div className="public-trivia-grid">{items.map((item) => <PublicTriviaCard key={item.id} item={item} />)}</div>;
}

export function PublicTriviaCard({ item }: { item: TriviaItem }) {
  const [revealed, setRevealed] = useState(false);
  const initialRender = useRef(true);
  const revealButton = useRef<HTMLButtonElement>(null);
  const questionButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (initialRender.current) {
      initialRender.current = false;
      return;
    }
    (revealed ? questionButton : revealButton).current?.focus();
  }, [revealed]);

  return (
    <article className={`public-trivia-card${revealed ? " revealed" : ""}`}>
      <div className="flashcard-inner">
        <div className="flashcard-face flashcard-front" aria-hidden={revealed}>
          <p className={`asked-by${item.asker ? "" : " empty"}`} aria-hidden={item.asker ? undefined : true}>
            {item.asker ? `Asked by ${triviaAskerName(item)}` : "\u00a0"}
          </p>
          <h3>{item.question ?? "Untitled question"}</h3>
          <button ref={revealButton} className="reveal-button" type="button" tabIndex={revealed ? -1 : 0} onClick={() => setRevealed(true)}>Reveal answer</button>
        </div>
        <div className="flashcard-face flashcard-back" aria-hidden={!revealed}>
          <div className="flashcard-question"><h3>{item.question ?? "Untitled question"}</h3></div>
          <div className="answer"><p>{item.answer ?? "No answer provided."}</p></div>
          <button ref={questionButton} className="show-question-button" type="button" tabIndex={revealed ? 0 : -1} onClick={() => setRevealed(false)}>Show question</button>
        </div>
      </div>
    </article>
  );
}
