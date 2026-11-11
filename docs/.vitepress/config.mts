import { defineConfig, type HeadConfig } from 'vitepress'

const SITE = 'https://pauloberezini.github.io/hermes-synapse'
const TITLE = 'Hermes Synapse'
const DESCRIPTION =
  'Runtime governance and a human approval layer for AI agents. Self-hosted DAG orchestrator with payload-bound approvals, an append-only decision log, and offline verification.'
const OG_IMAGE = `${SITE}/og-image.png`
const KEYWORDS =
  'Hermes Synapse, AI agent governance, human-in-the-loop, approval gate, runtime governance, multi-agent orchestrator, DAG agents, MCP, decision log, payload hash, bundle hash, self-hosted AI, Paperclip governance, SupplyAlpha'

const jsonLd = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: TITLE,
  applicationCategory: 'DeveloperApplication',
  operatingSystem: 'Linux, Docker',
  softwareVersion: '1.5.0',
  offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
  license: 'https://opensource.org/licenses/MIT',
  url: `${SITE}/`,
  downloadUrl: 'https://github.com/pauloberezini/hermes-synapse',
  codeRepository: 'https://github.com/pauloberezini/hermes-synapse',
  description: DESCRIPTION,
  screenshot: OG_IMAGE,
  keywords: KEYWORDS,
  author: {
    '@type': 'Person',
    name: 'Pavel Bereznichenko',
    url: 'https://github.com/pauloberezini',
  },
  creator: {
    '@type': 'Organization',
    name: 'SupplyAlpha.ai',
    url: 'https://supplyalpha.ai',
  },
}

function canonicalFor(relativePath: string): string {
  const normalized = relativePath.replace(/\\/g, '/')
  if (normalized === 'index.md') return `${SITE}/`
  const withoutExt = normalized.replace(/\.md$/, '')
  return `${SITE}/${withoutExt}.html`
}

export default defineConfig({
  title: TITLE,
  titleTemplate: ':title | Hermes Synapse',
  description: DESCRIPTION,
  lang: 'en-US',
  base: '/hermes-synapse/',
  srcExclude: ['**/specs/**'],
  ignoreDeadLinks: [/^https?:\/\/localhost/],
  lastUpdated: true,
  cleanUrls: false,
  sitemap: {
    hostname: 'https://pauloberezini.github.io/hermes-synapse/',
    transformItems: (items) =>
      items.map((item) => {
        const raw = item.url || '/'
        let path: string
        try {
          path = new URL(raw, 'https://pauloberezini.github.io').pathname
        } catch {
          path = raw.startsWith('/') ? raw : `/${raw}`
        }
        if (!path.startsWith('/hermes-synapse')) {
          path = `/hermes-synapse${path === '/' ? '/' : path}`
        }
        return { ...item, url: `https://pauloberezini.github.io${path}` }
      }),
  },
  head: [
    ['link', { rel: 'icon', href: '/hermes-synapse/favicon.svg', type: 'image/svg+xml' }],
    ['meta', { name: 'theme-color', content: '#00f0ff' }],
    ['meta', { name: 'author', content: 'Pavel Bereznichenko, SupplyAlpha.ai' }],
    ['meta', { name: 'keywords', content: KEYWORDS }],
    ['meta', { name: 'robots', content: 'index,follow' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:site_name', content: TITLE }],
    ['meta', { property: 'og:image', content: OG_IMAGE }],
    ['meta', { property: 'og:image:alt', content: 'Hermes Synapse Communication Link: Sys Ops waiting for human approval of df -h /' }],
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
    ['meta', { name: 'twitter:image', content: OG_IMAGE }],
    ['script', { type: 'application/ld+json' }, JSON.stringify(jsonLd)],
  ],
  transformHead({ pageData }) {
    const canonical = canonicalFor(pageData.relativePath)
    const pageTitle = pageData.title
      ? `${pageData.title} | ${TITLE}`
      : `${TITLE} | Runtime governance for AI agents`
    const pageDesc = pageData.description || DESCRIPTION
    const extra: HeadConfig[] = [
      ['link', { rel: 'canonical', href: canonical }],
      ['meta', { property: 'og:title', content: pageTitle }],
      ['meta', { property: 'og:description', content: pageDesc }],
      ['meta', { property: 'og:url', content: canonical }],
      ['meta', { name: 'twitter:title', content: pageTitle }],
      ['meta', { name: 'twitter:description', content: pageDesc }],
    ]
    return extra
  },
  themeConfig: {
    logo: { src: '/favicon.svg', alt: 'Hermes Synapse' },
    siteTitle: 'HERMES SYNAPSE',
    search: {
      provider: 'local',
    },
    nav: [
      { text: 'Home', link: '/' },
      { text: 'Quick start', link: '/guide/getting-started' },
      { text: 'Security', link: '/guide/security' },
      { text: 'Integrations', link: '/guide/integrations' },
      { text: 'Approvals', link: '/guide/approvals' },
      { text: 'GitHub', link: 'https://github.com/pauloberezini/hermes-synapse' },
    ],
    sidebar: [
      {
        text: 'Start here',
        items: [
          { text: 'Quick start', link: '/guide/getting-started' },
          { text: 'Approvals walkthrough', link: '/guide/approvals' },
          { text: 'Video demos', link: '/videos/' },
        ],
      },
      {
        text: 'Product',
        items: [
          { text: 'Security model', link: '/guide/security' },
          { text: 'Integrations', link: '/guide/integrations' },
          { text: 'Budgeting and governance', link: '/guide/paperclip-governance' },
          { text: 'Task engine and Kanban', link: '/guide/task-engine' },
          { text: 'Agent mesh and SDK', link: '/guide/agent-mesh' },
        ],
      },
    ],
    socialLinks: [
      { icon: 'github', link: 'https://github.com/pauloberezini/hermes-synapse' },
    ],
    outline: { level: [2, 3] },
    footer: {
      message: 'MIT License. Runtime governance for AI agents.',
      copyright: 'Copyright 2026 Pavel Bereznichenko / SupplyAlpha.ai',
    },
  },
})
