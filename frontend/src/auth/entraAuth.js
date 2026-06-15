import { LogLevel } from '@azure/msal-browser';
import { frontendUrl } from "@/config";
import tfconfig from '@/../terraform.config.json';
import appInsights from '@/log/appInsights';


// Redirect URI = the deployed origin + sub-path (e.g.
// https://datapi.galaxus.box/ultimate-web-stack-dev/), which is what is
// registered on the Entra app reg. Falls back to frontendUrl outside the browser.
const appRedirectUri = (typeof window !== 'undefined')
  ? window.location.origin + import.meta.env.BASE_URL
  : frontendUrl;

export const msalConfig = () =>{
  console.log("redirect uri:" + appRedirectUri);
  return {
    auth: {
      clientId: tfconfig.client_id.value,
      authority: `https://login.microsoftonline.com/${tfconfig.tenant_id.value}/v2.0`,
      redirectUri: appRedirectUri,
      postLogoutRedirectUri: appRedirectUri,
    },
    cache: {
      cacheLocation: 'localStorage',
      storeAuthStateInCookie: false,
    },
    system: {
      loggerOptions: {
        loggerCallback: (level, message, containsPii) => {
          if (containsPii) return;
          console[level === LogLevel.Error ? 'error' : 'info'](message);
        }
      }
    }
  };
};


export const loginRequest = {
  // Not part of the trimmed k8s terraform output; default to a basic Graph scope.
  scopes: tfconfig.requested_graph_api_delegated_permissions?.value ?? ['User.Read'],
};

export const retrieveTokenForBackend = async (instance, extraScopes = []) => {
  appInsights.trackEvent({ name: 'MSAL Retrieving Token' });
  const account = instance.getActiveAccount();
  const tokenResponse = await instance.acquireTokenSilent({
    scopes: [tfconfig.oauth2_permission_scope_uri.value, ...extraScopes],
    account: account,
  });
  return tokenResponse.accessToken;
}

export const retrieveTokenForGraph = async (instance, extraScopes = []) => {
  appInsights.trackEvent({ name: 'MSAL Retrieving Graph Token' });
  const account = instance.getActiveAccount();
  
  // For Graph API, use the graph scopes - not the API scope
  const defaultGraphScopes = ['https://graph.microsoft.com/.default'];
  const scopesToRequest = [...defaultGraphScopes] //, ...extraScopes];
  
  try {
    const tokenResponse = await instance.acquireTokenSilent({
      scopes: scopesToRequest,
      account: account
    });
    
    return tokenResponse.accessToken;
  } catch (error) {
    appInsights.trackException({ 
      exception: error,
      properties: { 
        operation: 'retrieveTokenForGraph', 
        scopes: scopesToRequest.join(',') 
      }
    });
    
    // If silent token acquisition fails, you might want to try interactive
    if (error.name === "InteractionRequiredAuthError") {
      // fallback to interactive method
      const interactiveResponse = await instance.acquireTokenPopup({
        scopes: scopesToRequest,
      });
      return interactiveResponse.accessToken;
    }
    
    throw error;
  }
};


