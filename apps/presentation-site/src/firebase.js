import { initializeApp } from 'firebase/app';
import { initializeAppCheck, ReCaptchaV3Provider } from 'firebase/app-check';
import { getToken } from 'firebase/app-check';
const config={apiKey:import.meta.env.VITE_FIREBASE_API_KEY,authDomain:import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,projectId:import.meta.env.VITE_FIREBASE_PROJECT_ID,appId:import.meta.env.VITE_FIREBASE_APP_ID,storageBucket:import.meta.env.VITE_FIREBASE_STORAGE_BUCKET};
const configured=Boolean(config.apiKey&&config.authDomain&&config.projectId&&config.appId);
const app=configured?initializeApp(config):null;
let appCheck=null;
if(app&&import.meta.env.VITE_RECAPTCHA_V3_SITE_KEY){appCheck=initializeAppCheck(app,{provider:new ReCaptchaV3Provider(import.meta.env.VITE_RECAPTCHA_V3_SITE_KEY),isTokenAutoRefreshEnabled:true});}
export async function appCheckHeaders(){if(!appCheck)return {};try{const t=await getToken(appCheck,false);return {'X-Firebase-AppCheck':t.token};}catch{return {};}}
