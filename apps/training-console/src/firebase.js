import { initializeApp } from 'firebase/app';
import { getAuth } from 'firebase/auth';
import { initializeAppCheck, ReCaptchaV3Provider } from 'firebase/app-check';

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
};
const configured = Boolean(config.apiKey && config.authDomain && config.projectId && config.appId);
export const firebaseApp = configured ? initializeApp(config) : null;
export const auth = firebaseApp ? getAuth(firebaseApp) : null;
let appCheck = null;
if (firebaseApp && import.meta.env.VITE_RECAPTCHA_V3_SITE_KEY) {
  appCheck = initializeAppCheck(firebaseApp, {
    provider: new ReCaptchaV3Provider(import.meta.env.VITE_RECAPTCHA_V3_SITE_KEY),
    isTokenAutoRefreshEnabled: true,
  });
}
export { configured, appCheck };
