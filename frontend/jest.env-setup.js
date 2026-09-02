// Force NODE_ENV=test BEFORE any other module loads. Without this, when the
// container (or any host that inherits NODE_ENV=production from the system)
// runs `npx jest`, React resolves to its production bundle and `React.act`
// is undefined — which makes every `render(...)` from @testing-library/react
// throw `TypeError: React.act is not a function` (jest 30 + react 19 + react-dom
// 19 stack). This file is wired as the FIRST `setupFiles` entry so it runs
// before jest.setup.js (setupFilesAfterEnv) and therefore before React is
// required by @testing-library/jest-dom or any test file.
process.env.NODE_ENV = 'test';
