import { ApplicationInsights } from '@microsoft/applicationinsights-web';
import tfconfig from '@/../terraform.config.json';

// This k8s deployment uses OpenTelemetry, not Azure App Insights, so the
// connection string is usually absent from the terraform output. Initialise
// the real SDK only when one is provided; otherwise export a no-op shim with
// the same surface the app calls (matches src/mock/appInsights.js).
const connectionString = tfconfig.application_insights_connection_string?.value;

let appInsights;

if (connectionString) {
  appInsights = new ApplicationInsights({
    config: {
      connectionString,
      enableAutoRouteTracking: true,
      disableFlushOnBeforeUnload: true,
      disablePageUnloadEvents: true,
    },
  });
  appInsights.loadAppInsights();
} else {
  const noop = () => {};
  appInsights = {
    trackEvent: noop,
    trackException: noop,
    trackPageView: noop,
    trackMetric: noop,
    setAuthenticatedUserContext: noop,
    flush: noop,
    loadAppInsights: () => appInsights,
    config: {},
  };
}

export default appInsights;
