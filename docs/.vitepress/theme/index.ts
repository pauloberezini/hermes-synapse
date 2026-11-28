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
          'Known limits today: agents that run generated Python (Code Engineer, Data Analyst) are outside the gate. Agents have to run inside Hermes. The log is tamper-evident when you pin its head hash, not signed. Per-role approval rights are planned, not shipped. One maintainer.',
        ),
    }),
  enhanceApp({ app }) {
    app.component('YouTube', YouTube)
  },
}
