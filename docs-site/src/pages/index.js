import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import HomepageFeatures from '@site/src/components/HomepageFeatures';
import Heading from '@theme/Heading';

import styles from './index.module.css';

function HomepageHeader() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className="container">
        {/* P13-4.3: Add ArgusAI logo to hero section */}
        <img
          src="/ArgusAI/img/logo.png"
          alt="ArgusAI Logo"
          className={styles.heroLogo}
          width={120}
          height={120}
        />
        <Heading as="h1" className="hero__title">
          {siteConfig.title}
        </Heading>
        <p className="hero__subtitle">{siteConfig.tagline}</p>
        <p className={styles.heroDescription}>
          Transform your security cameras into an intelligent monitoring system.
          ArgusAI analyzes video feeds from UniFi Protect, RTSP, and USB cameras,
          providing natural language descriptions of events powered by leading AI providers.
        </p>
        <div className={styles.buttons}>
          <Link
            className="button button--secondary button--lg"
            to="/docs/intro">
            Get Started
          </Link>
          <Link
            className="button button--outline button--secondary button--lg"
            href="https://github.com/project-argusai/ArgusAI">
            View on GitHub
          </Link>
        </div>
      </div>
    </header>
  );
}

function StatsSection() {
  const stats = [
    { value: '4', label: 'AI Providers', description: 'OpenAI, Grok, Claude, Gemini' },
    { value: '<5s', label: 'Event Latency', description: 'Real-time processing' },
    { value: '3', label: 'Camera Types', description: 'Protect, RTSP, USB' },
    { value: '5', label: 'Apple Platforms', description: 'iOS, iPad, Watch, TV, Mac' },
  ];

  return (
    <section className={styles.stats}>
      <div className="container">
        <div className={styles.statsGrid}>
          {stats.map((stat, idx) => (
            <div key={idx} className={styles.statCard}>
              <div className={styles.statValue}>{stat.value}</div>
              <div className={styles.statLabel}>{stat.label}</div>
              <div className={styles.statDescription}>{stat.description}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function Home() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title={`${siteConfig.title} - AI-Powered Home Security`}
      description="ArgusAI is an AI-powered event detection system for home security. Analyze video feeds from UniFi Protect, RTSP, and USB cameras with multi-provider AI.">
      <HomepageHeader />
      <main>
        <StatsSection />
        <HomepageFeatures />
        <section className={styles.highlights}>
          <div className="container">
            <Heading as="h2" className={styles.sectionTitle}>Why ArgusAI?</Heading>
            <div className="row">
              <div className="col col--6">
                <Heading as="h3">Intelligent Analysis</Heading>
                <ul>
                  <li><strong>Multi-Frame Analysis:</strong> Adaptive frame sampling captures the right moments</li>
                  <li><strong>Context-Aware:</strong> AI uses camera location and time for better descriptions</li>
                  <li><strong>Daily Summaries:</strong> AI-generated activity digests for each day</li>
                  <li><strong>Confidence Scoring:</strong> Know when the AI is uncertain</li>
                  <li><strong>SSL/HTTPS:</strong> Secure connections with certificate management</li>
                </ul>
              </div>
              <div className="col col--6">
                <Heading as="h3">Flexible Camera Support</Heading>
                <ul>
                  <li><strong>UniFi Protect:</strong> Native integration with WebSocket events</li>
                  <li><strong>RTSP Cameras:</strong> Any IP camera with RTSP stream support</li>
                  <li><strong>USB Webcams:</strong> Direct capture for local cameras</li>
                  <li><strong>ONVIF Discovery:</strong> Auto-discover compatible cameras</li>
                </ul>
                <Heading as="h3" style={{marginTop: '1.5rem'}}>Smart Home Integration</Heading>
                <ul>
                  <li><strong>Home Assistant:</strong> MQTT with auto-discovery</li>
                  <li><strong>Apple HomeKit:</strong> Motion sensors and camera streaming</li>
                </ul>
                <Heading as="h3" style={{marginTop: '1.5rem'}}>Native Apple Apps</Heading>
                <ul>
                  <li><strong>iPhone & iPad:</strong> Push notifications, widgets, Siri</li>
                  <li><strong>Apple Watch:</strong> Complications, haptic alerts</li>
                  <li><strong>Apple TV:</strong> Dashboard, video playback</li>
                  <li><strong>Cloud Relay:</strong> Secure remote access via Cloudflare</li>
                </ul>
              </div>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
