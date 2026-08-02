<template>
  <div class="video-container">
    <iframe
      :src="'https://www.youtube-nocookie.com/embed/' + id"
      :title="title || 'YouTube video player'"
      frameborder="0"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
      allowfullscreen
    ></iframe>
  </div>
</template>

<script setup>
defineProps({
  id: {
    type: String,
    required: true
  },
  title: {
    type: String,
    default: ''
  }
})
</script>

<style scoped>
.video-container {
  position: relative;
  width: 100%;
  padding-bottom: 56.25%; /* 16:9 Aspect Ratio */
  height: 0;
  margin: 1.5rem 0;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(0, 240, 255, 0.4);
  box-shadow: 0 0 20px rgba(0, 240, 255, 0.15);
}

.video-container iframe {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}
</style>
