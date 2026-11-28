import DefaultTheme from 'vitepress/theme'
import { h } from 'vue'
import YouTube from './YouTube.vue'
import './custom.css'

export default {
  extends: DefaultTheme,
  Layout: () =>
    h(DefaultTheme.Layout, null, {
      'home-hero-actions-after': () =>
        h(
          'p',
          { class: 'hero-limits' },
          'Known limits today: Approvals cover agents running in Hermes, including their calls to external MCP tools; there is no gateway in front of Claude Code, Cursor or other MCP clients. The approve endpoint does not check roles yet. The log is tamper-evident when you pin its head hash, not signed. One maintainer.',
        ),
    }),
  enhanceApp({ app }) {
    app.component('YouTube', YouTube)
  },
}
