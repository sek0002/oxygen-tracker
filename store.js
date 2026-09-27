import {config} from './config.js';
export const configured = true;
export async function rpc(name, args) {
  let response;
  try {
    response = await fetch(`${config.apiBase}/api/${name}`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(args), signal:AbortSignal.timeout(15000)
    });
  } catch { throw new Error('Cannot reach the shared database. Check your connection and retry.'); }
  let data;
  try { data = await response.json(); } catch { throw new Error('The database server is not connected. Please check the deployment.'); }
  if (!response.ok || data.error) throw new Error(data.error || 'The database could not save this change.');
  return data;
}
