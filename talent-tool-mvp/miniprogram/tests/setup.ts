// Provide a baseline `uni` global for tests that load store/api modules
// without going through the full uni-app runtime.
const noop = () => {};
const uniStub: Record<string, any> = {
  request: noop,
  uploadFile: noop,
  downloadFile: noop,
  getStorageSync: () => '',
  setStorageSync: noop,
  removeStorageSync: noop,
  showToast: noop,
  showModal: noop,
  showActionSheet: noop,
  reLaunch: noop,
  navigateTo: noop,
  redirectTo: noop,
  navigateBack: noop,
  login: noop,
  getUserProfile: noop,
  startRecord: noop,
  stopRecord: noop,
  getSystemInfoSync: () => ({ platform: 'devtools', screenWidth: 375 }),
};

if (typeof (globalThis as any).uni === 'undefined') {
  (globalThis as any).uni = uniStub;
}