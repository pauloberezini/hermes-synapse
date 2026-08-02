import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'Hermes Synapse',
  description: 'Autonomous Multi-Agent Mesh & Paperclip Governance System',
  base: '/hermes-synapse/',
  head: [
    ['link', { rel: 'icon', href: '/favicon.ico' }],
    ['meta', { name: 'theme-color', content: '#00f0ff' }]
  ],
  themeConfig: {
    logo: '/logo.png',
    siteTitle: 'HERMES SYNAPSE',
    nav: [
      { text: 'Home', link: '/' },
      { text: 'Guide', link: '/guide/getting-started' },
      { text: 'Paperclip Features', link: '/guide/paperclip-governance' },
      { text: 'Video Tutorials 🎥', link: '/videos/' },
      { text: 'GitHub', link: 'https://github.com/pauloberezini/hermes-synapse' }
    ],
    sidebar: [
      {
        text: '🚀 Getting Started',
        items: [
          { text: 'Introduction & Overview', link: '/guide/getting-started' },
          { text: 'Architecture & Agent Mesh', link: '/guide/agent-mesh' }
        ]
      },
      {
        text: '🛡️ Paperclip Governance',
        items: [
          { text: 'Budgeting & Approvals', link: '/guide/paperclip-governance' },
          { text: 'Task Engine & Kanban', link: '/guide/task-engine' }
        ]
      },
      {
        text: '🎥 Video Walkthroughs',
        items: [
          { text: 'YouTube Tutorials & Demos', link: '/videos/' }
        ]
      }
    ],
    socialLinks: [
      { icon: 'github', link: 'https://github.com/pauloberezini/hermes-synapse' }
    ],
    footer: {
      message: 'Released under the MIT License.',
      copyright: 'Copyright © 2026 Hermes Synapse Contributors'
    }
  }
})
