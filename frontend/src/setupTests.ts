import '@testing-library/jest-dom';

window.HTMLElement.prototype.scrollIntoView = function() {};

class TestResizeObserver implements ResizeObserver {
  constructor(_callback: ResizeObserverCallback) {}
  observe(_target: Element, _options?: ResizeObserverOptions) {}
  unobserve(_target: Element) {}
  disconnect() {}
}

globalThis.ResizeObserver = TestResizeObserver as typeof ResizeObserver;
globalThis.requestAnimationFrame = () => 1;
globalThis.cancelAnimationFrame = () => undefined;
