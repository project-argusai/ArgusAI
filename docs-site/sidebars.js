/**
 * Creating a sidebar enables you to:
 - create an ordered group of docs
 - render a sidebar for each doc of that group
 - provide next/previous navigation

 The sidebars can be generated from the filesystem, or explicitly defined here.

 Create as many sidebars as you want.
 */

// @ts-check

/** @type {import('@docusaurus/plugin-content-docs').SidebarsConfig} */
const sidebars = {
  tutorialSidebar: [
    'intro',
    {
      type: 'category',
      label: 'Getting Started',
      items: ['getting-started/installation', 'getting-started/configuration'],
    },
    {
      type: 'category',
      label: 'Deployment',
      items: [
        'getting-started/docker-deployment',
        'getting-started/kubernetes-deployment',
        'getting-started/helm-deployment',
        'getting-started/ci-cd',
      ],
    },
    {
      type: 'category',
      label: 'How to Use',
      items: [
        'how-to-use/index',
        'how-to-use/dashboard',
        'how-to-use/events',
        'how-to-use/cameras',
        'how-to-use/entities',
        'how-to-use/alert-rules',
        'how-to-use/settings',
        'how-to-use/summaries',
      ],
    },
    {
      type: 'category',
      label: 'Features',
      items: [
        'features/unifi-protect',
        'features/ai-analysis',
        'features/entity-recognition',
        'features/notifications',
      ],
    },
    {
      type: 'category',
      label: 'Integrations',
      items: [
        'integrations/home-assistant',
        'integrations/homekit',
        'integrations/native-apple-apps',
        'integrations/cloudflare-tunnel',
      ],
    },
    {
      type: 'category',
      label: 'API Reference',
      items: ['api/overview'],
    },
    'troubleshooting',
  ],
};

module.exports = sidebars;
