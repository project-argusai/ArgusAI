import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

const FeatureList = [
  {
    title: 'AI-Powered Analysis',
    Svg: require('@site/static/img/undraw_artificial_intelligence.svg').default,
    description: (
      <>
        Advanced multi-frame video analysis with GPT-4, Claude, Grok, and Gemini.
        Get intelligent descriptions of security events with confidence scoring
        and entity recognition.
      </>
    ),
  },
  {
    title: 'UniFi Protect Integration',
    Svg: require('@site/static/img/undraw_security.svg').default,
    description: (
      <>
        Native integration with UniFi Protect cameras. Real-time event detection,
        smart motion filtering, and seamless camera management through a unified
        dashboard.
      </>
    ),
  },
  {
    title: 'Smart Home Ready',
    Svg: require('@site/static/img/undraw_smart_home.svg').default,
    description: (
      <>
        Connect to Home Assistant via MQTT with auto-discovery. Full Apple HomeKit
        support for motion sensors, doorbells, and camera streaming. Push notifications
        with thumbnails.
      </>
    ),
  },
];

function Feature({Svg, title, description}) {
  return (
    <div className={clsx('col col--4')}>
      <div className="text--center">
        <Svg className={styles.featureSvg} role="img" />
      </div>
      <div className="text--center padding-horiz--md">
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures() {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}
