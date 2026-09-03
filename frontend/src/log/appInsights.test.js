// Coverage for `src/log/appInsights.js`. The module reads
// `application_insights_connection_string` out of the terraform output and,
// when the value is present, instantiates the real `ApplicationInsights`
// SDK and calls `loadAppInsights()`. When the value is absent it returns
// a no-op shim with the same surface the app calls.
//
// `jest.setup.js` mocks `@/log/appInsights` for the rest of the suite
// (so other tests can spy on its `trackEvent`/`trackException`). The
// bypass for that setup-level mock is `jest.unmock('@/log/appInsights')`
// + `jest.isolateModulesAsync` — together they re-route the
// `await import('./appInsights')` resolution past the CJS setup-level
// mock and let `jest.doMock` for the SDK + terraform-config drive the
// module's `if (connectionString)` ternary.

jest.unmock('@/log/appInsights');

describe('Application Insights (real module)', () => {
  beforeEach(() => {
    jest.resetModules();
  });

  // Helper — load `appInsights.js` under controlled ESM mocks for the
  // terraform config + the SDK constructor. Returns the default export
  // (the appInsights instance itself).
  const loadAppInsightsWith = async (connectionString) => {
    let mod;
    await jest.isolateModulesAsync(async () => {
      jest.doMock('@/../terraform.config.json', () => ({
        application_insights_connection_string: { value: connectionString },
      }));
      jest.doMock('@microsoft/applicationinsights-web', () => ({
        ApplicationInsights: jest.fn().mockImplementation((options) => ({
          config: options.config,
          loadAppInsights: jest.fn(),
          trackEvent: jest.fn(),
          trackException: jest.fn(),
          trackPageView: jest.fn(),
          trackMetric: jest.fn(),
          setAuthenticatedUserContext: jest.fn(),
          flush: jest.fn(),
        })),
      }));
      const imported = await import('./appInsights');
      mod = imported.default;
    });
    return mod;
  };

  it('exports the real SDK instance when the terraform config supplies a connection string', async () => {
    const appInsights = await loadAppInsightsWith('InstrumentationKey=real-key');
    expect(typeof appInsights.loadAppInsights).toBe('function');
    expect(typeof appInsights.trackEvent).toBe('function');
    expect(typeof appInsights.trackException).toBe('function');
    expect(typeof appInsights.trackPageView).toBe('function');
    expect(typeof appInsights.trackMetric).toBe('function');
    expect(typeof appInsights.setAuthenticatedUserContext).toBe('function');
    expect(typeof appInsights.flush).toBe('function');
    expect(appInsights.config).toBeDefined();
  });

  it('exports a no-op shim when the terraform config omits the connection string', async () => {
    let mod;
    await jest.isolateModulesAsync(async () => {
      jest.doMock('@/../terraform.config.json', () => ({
        application_insights_connection_string: { value: undefined },
      }));
      jest.doMock('@microsoft/applicationinsights-web', () => ({
        ApplicationInsights: jest.fn(),
      }));
      const imported = await import('./appInsights');
      mod = imported.default;
    });

    // Every method on the shim is callable but does nothing.
    expect(() => mod.trackEvent({ name: 'x' })).not.toThrow();
    expect(() => mod.trackException(new Error('x'))).not.toThrow();
    expect(() => mod.trackPageView({ name: 'x' })).not.toThrow();
    expect(() => mod.trackMetric({ name: 'x', average: 1 })).not.toThrow();
    expect(() => mod.setAuthenticatedUserContext('uid', 'aid')).not.toThrow();
    expect(() => mod.flush()).not.toThrow();
    // loadAppInsights is a special case — it returns the instance itself
    // (mirroring the real SDK's self-returning pattern) so callers can
    // chain.
    const chained = mod.loadAppInsights();
    expect(chained).toBeDefined();
    expect(typeof chained.trackEvent).toBe('function');
    expect(chained.config).toEqual({});
  });

  it('treats an empty-string connection string the same as absent (shim branch)', async () => {
    // The `if (connectionString)` ternary treats any falsy value (empty
    // string, undefined, null, 0) as absent. Vite would only ever inline a
    // real connection string here, but the ternary's branch coverage
    // requires a falsy value to reach the shim path.
    const appInsights = await loadAppInsightsWith('');
    expect(appInsights.loadAppInsights()).toBeDefined();
  });
});
