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
        <Heading as="h1" className="hero__title">
          {siteConfig.title}
        </Heading>
        <p className="hero__subtitle">{siteConfig.tagline}</p>
        <div className={styles.buttons}>
          <Link
            className="button button--secondary button--lg"
            to="/docs/intro">
            Get Started
          </Link>
          <Link
            className="button button--outline button--secondary button--lg"
            style={{marginLeft: '1rem'}}
            href="https://github.com/bbengt1/argusai">
            View on GitHub
          </Link>
        </div>
      </div>
    </header>
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
        <HomepageFeatures />
        <section className={styles.highlights}>
          <div className="container">
            <div className="row">
              <div className="col col--6">
                <Heading as="h2">Key Features</Heading>
                <ul>
                  <li><strong>Multi-Provider AI:</strong> OpenAI GPT-4, xAI Grok, Anthropic Claude, Google Gemini</li>
                  <li><strong>Smart Analysis:</strong> Multi-frame video analysis with adaptive frame sampling</li>
                  <li><strong>Entity Recognition:</strong> Track people, vehicles, and packages over time</li>
                  <li><strong>Daily Summaries:</strong> AI-generated activity digests</li>
                  <li><strong>Push Notifications:</strong> Real-time alerts with thumbnails</li>
                  <li><strong>SSL/HTTPS:</strong> Secure connections with certificate management</li>
                </ul>
              </div>
              <div className="col col--6">
                <Heading as="h2">Supported Cameras</Heading>
                <ul>
                  <li><strong>UniFi Protect:</strong> Native integration with WebSocket events</li>
                  <li><strong>RTSP Cameras:</strong> Any IP camera with RTSP stream support</li>
                  <li><strong>USB Webcams:</strong> Direct capture for local cameras</li>
                  <li><strong>ONVIF Discovery:</strong> Auto-discover compatible cameras</li>
                </ul>
                <Heading as="h2" style={{marginTop: '1.5rem'}}>Integrations</Heading>
                <ul>
                  <li><strong>Home Assistant:</strong> MQTT with auto-discovery</li>
                  <li><strong>Apple HomeKit:</strong> Motion sensors and camera streaming</li>
                </ul>
              </div>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
