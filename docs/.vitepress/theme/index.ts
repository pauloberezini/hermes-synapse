import DefaultTheme from 'vitepress/theme'
import YouTube from './YouTube.vue'
import './custom.css'

export default {
  extends: DefaultTheme,
  enhanceApp({ app }) {
    app.component('YouTube', YouTube)
  }
}
