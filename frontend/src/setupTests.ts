import '@testing-library/jest-dom';

window.HTMLElement.prototype.scrollIntoView = function() {};

// jsdom does not implement ResizeObserver — stub it for canvas-based components
(window as any).ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
