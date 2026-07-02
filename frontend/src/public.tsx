import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ExternalLink, Facebook, Instagram, Mail, Menu, MessageCircle, Youtube, X } from "lucide-react";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";
import { getPublicEpisode, getPublicEpisodeTrivia, listPublicEpisodes, listPublicTrivia } from "./api";
import type { PublicEpisode, TriviaItem } from "./types";
import { formatDate, triviaAskerName } from "./workflow";
import { QueryState } from "./ui";
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
          <NavLink to="/episodes">Episodes</NavLink>
          <NavLink to="/trivia">Trivia</NavLink>
          <NavLink to="/about">About us</NavLink>
          <NavLink className="admin-link" to="/admin">Admin</NavLink>
        </nav>
      </header>
      <main><Outlet /></main>
      <footer className="public-footer">
        <img src={logoUrl} alt="" />
        <p>Questions worth asking. Answers worth remembering.</p>
        <div className="footer-links"><Link to="/about">About us</Link><Link to="/admin">Podcast admin</Link></div>
      </footer>
    </div>
  );
}

export function HomePage() {
  const episodes = useQuery({ queryKey: ["public", "episodes"], queryFn: listPublicEpisodes });
  const trivia = useQuery({ queryKey: ["public", "trivia", 6], queryFn: () => listPublicTrivia(6) });
  const latest = episodes.data?.[0];

  return (
    <>
      <section className="home-hero">
        <div className="hero-art"><img src={thumbnailUrl} alt="Are You Quizzing Me podcast artwork" /></div>
        <div className="hero-copy">
          <p className="comic-kicker">The podcast that asks</p>
          <h1>Are You Quizzing Me?</h1>
          {latest ? (
            <>
              <p className="episode-label">Latest: Episode {latest.episode_number}</p>
              <h2>{latest.episode_title}</h2>
              <p>{latest.episode_description}</p>
              <div className="hero-actions">
                <Link className="button primary" to={`/episodes/${latest.id}`}>Explore episode <ArrowRight size={18} /></Link>
                {latest.source_url && <a className="button light" href={latest.source_url} target="_blank" rel="noreferrer">Listen <ExternalLink size={17} /></a>}
              </div>
            </>
          ) : !episodes.isLoading && !episodes.error ? (
            <p>New episodes and questions are on the way.</p>
          ) : null}
        </div>
      </section>
      <div className="public-content">
        <QueryState query={episodes} feature="The episode showcase" empty="No published episodes yet.">
          {(items) => <EpisodeStrip episodes={items.slice(0, 3)} />}
        </QueryState>
        <section className="editorial-section">
          <div className="section-title-row"><div><p className="eyebrow">Test yourself</p><h2>Questions from the show</h2></div><Link to="/trivia">All trivia <ArrowRight size={16} /></Link></div>
          <QueryState query={trivia} feature="Featured trivia" empty="No published trivia yet.">
            {(items) => <TriviaGrid items={items} />}
          </QueryState>
        </section>
      </div>
    </>
  );
}

export function PublicEpisodesPage() {
  const episodes = useQuery({ queryKey: ["public", "episodes"], queryFn: listPublicEpisodes });
  return (
    <PublicPageHeader eyebrow="Listen and explore" title="Episodes" intro="Every conversation, every question, and the trivia that came out of it.">
      <QueryState query={episodes} feature="The episode archive" empty="No published episodes yet.">
        {(items) => <div className="episode-archive">{items.map((episode) => <EpisodeRow key={episode.id} episode={episode} />)}</div>}
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
              <img src={thumbnailUrl} alt="Are You Quizzing Me podcast artwork" />
              <div><p className="eyebrow">Episode {item.episode_number}</p><h1>{item.episode_title}</h1><p className="episode-date">{formatDate(item.published_at)}</p><p>{item.episode_description}</p><p className="speaker-line">With {item.speakers.map((speaker) => speaker.name).join(", ") || "the AYQM panel"}</p>{item.source_url && <a className="button primary" href={item.source_url} target="_blank" rel="noreferrer">Listen to episode <ExternalLink size={17} /></a>}</div>
            </header>
            <section className="editorial-section"><div className="section-title-row"><div><p className="eyebrow">Play along</p><h2>Trivia from this episode</h2></div></div><QueryState query={trivia} feature="Episode trivia" empty="No trivia has been published for this episode.">{(items) => <TriviaGrid items={items} />}</QueryState></section>
          </>
        )}
      </QueryState>
    </div>
  );
}

export function PublicTriviaPage() {
  const trivia = useQuery({ queryKey: ["public", "trivia", 24], queryFn: () => listPublicTrivia(24) });
  return (
    <PublicPageHeader eyebrow="Question bank" title="Trivia" intro="Questions pulled from conversations on Are You Quizzing Me. Make your guess, then reveal the answer.">
      <QueryState query={trivia} feature="The public trivia collection" empty="No trivia has been published yet.">{(items) => <TriviaGrid items={items} />}</QueryState>
    </PublicPageHeader>
  );
}

const guestHosts = [
  "Garry Leavy",
  "Aniruddha Sen Gupta",
  "Rajiv D'Silva",
  "Sai Visesh Suresh",
  "Hari Krishna Vetheranian",
  "Aishwarya Raman",
  "Berty Ashley"
];

export function AboutPage() {
  return (
    <div className="about-page">
      <section className="about-hero">
        <div className="about-hero-copy">
          <p className="eyebrow">About us</p>
          <h1>Two trivia lovers. Far too many cool facts.</h1>
          <p>Are You Quizzing Me? is an independent Indian trivia podcast created and hosted by Vineeth Nair and Aditya Kashyap.</p>
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
              <div className="host-initials" aria-hidden="true">VN</div>
              <p className="eyebrow">Co-founder and host</p>
              <h3>Vineeth Nair</h3>
              <p>Vineeth is a quizmaster, podcast co-founder and the voice behind more than 140 AYQM appearances. His public professional record also spans pathology and medical diagnostics, giving him a life outside the podcast that is every bit as detail-oriented.</p>
              <p>Alongside the main show, Vineeth has presented bonus mini episodes that dig into overlooked moments from Indian history. His interests on AYQM range across history, science, culture and the connections hiding between them.</p>
            </article>
            <article className="host-profile aditya">
              <div className="host-initials" aria-hidden="true">AK</div>
              <p className="eyebrow">Co-founder and host</p>
              <h3>Aditya Kashyap</h3>
              <p>Aditya is a quizmaster, seasoned host, actor and improv performer. He regularly conducts quizzes in Mumbai, has performed at comedy festivals across Asia, and has worked as an emcee for corporate events and educational institutions.</p>
              <p>He also teaches public speaking as a visiting faculty member and guest lecturer. On AYQM, that mix of quizzing, performance, improvisation and curiosity helps turn a collection of facts into a conversation.</p>
            </article>
          </div>
        </section>

        <section className="guest-section">
          <div><p className="eyebrow">Friends of the show</p><h2>Guest hosts so far</h2><p>Quizmasters and curious minds who have joined us behind the microphone.</p></div>
          <ol className="guest-list">{guestHosts.map((name, index) => <li key={name}><span>{String(index + 1).padStart(2, "0")}</span>{name}</li>)}</ol>
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
  return <article className="episode-tile"><Link to={`/episodes/${episode.id}`}><img src={thumbnailUrl} alt="" /><span>Episode {episode.episode_number}</span><h3>{episode.episode_title}</h3><p className="clamp">{episode.episode_description}</p></Link></article>;
}

function EpisodeRow({ episode }: { episode: PublicEpisode }) {
  return <article className="episode-row"><img src={thumbnailUrl} alt="" /><div><p className="eyebrow">Episode {episode.episode_number} · {formatDate(episode.published_at)}</p><h2><Link to={`/episodes/${episode.id}`}>{episode.episode_title}</Link></h2><p>{episode.episode_description}</p><span>{episode.trivia_count} trivia questions</span></div><Link className="icon-link" to={`/episodes/${episode.id}`} aria-label={`Open ${episode.episode_title}`}><ArrowRight /></Link></article>;
}

export function TriviaGrid({ items }: { items: TriviaItem[] }) {
  return <div className="public-trivia-grid">{items.map((item, index) => <PublicTriviaCard key={item.id} item={item} number={index + 1} />)}</div>;
}

export function PublicTriviaCard({ item, number }: { item: TriviaItem; number: number }) {
  const [revealed, setRevealed] = useState(false);
  return (
    <article className="public-trivia-card">
      <div className="question-number">Q{number.toString().padStart(2, "0")}</div>
      <p className="asked-by">Asked by {triviaAskerName(item)}</p>
      <h3>{item.question ?? "Untitled question"}</h3>
      {revealed ? <div className="answer"><span>Answer</span><p>{item.answer ?? "No answer provided."}</p></div> : <button className="reveal-button" type="button" onClick={() => setRevealed(true)}>Reveal answer</button>}
    </article>
  );
}
