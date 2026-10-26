import '@testing-library/jest-dom';

window.HTMLElement.prototype.scrollIntoView = function() {};

// jsdom does not implement ResizeObserver — stub it for canvas-based components
(window as any).ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// jsdom does not implement HTMLDialogElement methods
if (typeof HTMLDialogElement !== 'undefined') {
  HTMLDialogElement.prototype.showModal = HTMLDialogElement.prototype.showModal || function(this: any) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = HTMLDialogElement.prototype.close || function(this: any) {
    this.open = false;
  };
}

