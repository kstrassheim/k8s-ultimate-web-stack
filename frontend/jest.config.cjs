// jest.config.cjs
module.exports ={
    testEnvironment: "jsdom",
    moduleNameMapper: {
      "^@/../terraform.config.json$": "<rootDir>/mock/terraform.mock.config.json", // Add this line
      "^@/.*\\.css$": '<rootDir>/mock/styleMock.js',  // Handle @/App.css specifically
      "\\.(css|less|sass|scss)$": '<rootDir>/mock/styleMock.js',
      "\\.(jpg|jpeg|png|gif|svg)$": "<rootDir>/mock/fileMock.js",
      "^@/(.*)$": "<rootDir>/src/$1"
    },
    transform: {
        // Vite replaces `import.meta.env.MODE` at build time, but jest does
        // not — without a custom transform, `src/config.js` cannot load and
        // the whole file lands at 0% coverage. The pattern below points the
        // transform regex at the specific config file first; the second
        // `@swc/jest` entry handles everything else. The pattern matches
        // both relative and absolute paths because jest invokes the
        // transformer with the absolute filename.
        "(^|/)src/config\\.js$": "<rootDir>/jest.config-transformer.cjs",
        "^.+\\.[jt]sx?$": ["@swc/jest"],
        // react-router@8 transitively imports cookie-es@3.x, which is a
        // pure-ESM package shipping only `.mjs` files (no CJS build).
        // Default jest transform regex doesn't match `.mjs`, so add it.
        // SWC transforms the ESM `export`/`import` statements to CJS so
        // the jest runtime can load them.
        "^.+\\.mjs$": ["@swc/jest"]
    },
    transformIgnorePatterns: [
      "/node_modules/(?!module-to-transform)/"
    ],
    setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
    moduleDirectories: ['node_modules', 'src'],
    // Tell Jest to mock these files
    modulePathIgnorePatterns: ['<rootDir>/node_modules/'],
    moduleFileExtensions: ['js', 'jsx', 'json'],
    // Mock all files with __mocks__ folder
    automock: false,
    resetMocks: false,

    reporters: [
        "default",
        "<rootDir>/jest-preview-reporter.js"
      ],
    // ... existing config
    coveragePathIgnorePatterns: [
        "/node_modules/",
        "/mock/",         // Excludes all mock folders
        "\\\\mock\\\\"    // Windows path format (with escaped backslashes)
    ],
    collectCoverageFrom: [
        "src/**/*.{js,jsx}",  // Include all JS/JSX files in src
        "!src/**/*.test.{js,jsx}", // Exclude test files
        "!src/index.{js,jsx}", // Optionally exclude entry points
        "!**/node_modules/**",
        "!**/mock/**"  // Exclude mock files
      ],
      
      // Optional: Set coverage thresholds to make tests fail if coverage is too low
      coverageThreshold: {
        global: {
          statements: 70,
          branches: 60,
          functions: 70,
          lines: 70
        },
      }
  };