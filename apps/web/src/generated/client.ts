// Generated. Contract-only operations currently return 501; this is not a functioning product.
import type { Operations } from './contracts';
export class RelayClient {
  constructor(private baseUrl: string, private tokens: () => Promise<{idToken: string; appCheckToken: string}>) {}
  private async request<T>(method: string, path: string, input: {body?: unknown; query?: Record<string, string | number>; idempotencyKey?: string}): Promise<T> {
    const auth = await this.tokens();
    const url = new URL(this.baseUrl.replace(/\/$/, '') + path);
    for (const [key, value] of Object.entries(input.query ?? {})) url.searchParams.set(key, String(value));
    const headers: Record<string, string> = {'Authorization': `Bearer ${auth.idToken}`, 'X-Firebase-AppCheck': auth.appCheckToken};
    if (input.body !== undefined) headers['Content-Type'] = 'application/json';
    if (method === 'POST') headers['Idempotency-Key'] = input.idempotencyKey ?? crypto.randomUUID();
    const response = await fetch(url, {method, headers, body: input.body === undefined ? undefined : JSON.stringify(input.body), redirect: 'manual'});
    if (response.status === 302) throw new Error('PDF redirect requires explicit navigation to the authorized Location URL');
    if (!response.ok) {
      const delay = Number(response.headers.get('Retry-After'));
      const retryAfterSeconds = Number.isFinite(delay) && delay > 0 && delay <= 3600 ? Math.ceil(delay) : undefined;
      throw Object.assign(new Error(`Relay HTTP ${response.status}`), {status: response.status, retryAfterSeconds, problem: await response.json()});
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }
  E1(input: Operations['E1']['input']): Promise<Operations['E1']['output']> {
    return this.request("POST", "/api/v1/cases", input);
  }
  E2(input: Operations['E2']['input']): Promise<Operations['E2']['output']> {
    return this.request("GET", "/api/v1/cases/{caseId}".replace('{caseId}', encodeURIComponent(input.caseId)), input);
  }
  E3(input: Operations['E3']['input']): Promise<Operations['E3']['output']> {
    return this.request("DELETE", "/api/v1/cases/{caseId}".replace('{caseId}', encodeURIComponent(input.caseId)), input);
  }
  E4(input: Operations['E4']['input']): Promise<Operations['E4']['output']> {
    return this.request("PATCH", "/api/v1/cases/{caseId}/facts".replace('{caseId}', encodeURIComponent(input.caseId)), input);
  }
  E5(input: Operations['E5']['input']): Promise<Operations['E5']['output']> {
    return this.request("POST", "/api/v1/cases/{caseId}/messages".replace('{caseId}', encodeURIComponent(input.caseId)), input);
  }
  E6(input: Operations['E6']['input']): Promise<Operations['E6']['output']> {
    return this.request("POST", "/api/v1/cases/{caseId}/uploads".replace('{caseId}', encodeURIComponent(input.caseId)), input);
  }
  E7(input: Operations['E7']['input']): Promise<Operations['E7']['output']> {
    return this.request("POST", "/api/v1/cases/{caseId}/evidence/{evidenceId}/complete".replace('{caseId}', encodeURIComponent(input.caseId)).replace('{evidenceId}', encodeURIComponent(input.evidenceId)), input);
  }
  E8(input: Operations['E8']['input']): Promise<Operations['E8']['output']> {
    return this.request("GET", "/api/v1/cases/{caseId}/evidence/{evidenceId}".replace('{caseId}', encodeURIComponent(input.caseId)).replace('{evidenceId}', encodeURIComponent(input.evidenceId)), input);
  }
  E9(input: Operations['E9']['input']): Promise<Operations['E9']['output']> {
    return this.request("POST", "/api/v1/cases/{caseId}/evidence/{evidenceId}/confirm".replace('{caseId}', encodeURIComponent(input.caseId)).replace('{evidenceId}', encodeURIComponent(input.evidenceId)), input);
  }
  E10(input: Operations['E10']['input']): Promise<Operations['E10']['output']> {
    return this.request("POST", "/api/v1/cases/{caseId}/process".replace('{caseId}', encodeURIComponent(input.caseId)), input);
  }
  E11(input: Operations['E11']['input']): Promise<Operations['E11']['output']> {
    return this.request("GET", "/api/v1/jobs/{jobId}".replace('{jobId}', encodeURIComponent(input.jobId)), input);
  }
  E12(input: Operations['E12']['input']): Promise<Operations['E12']['output']> {
    return this.request("GET", "/api/v1/cases/{caseId}/plan".replace('{caseId}', encodeURIComponent(input.caseId)), input);
  }
  E13(input: Operations['E13']['input']): Promise<Operations['E13']['output']> {
    return this.request("POST", "/api/v1/cases/{caseId}/plan/rerun".replace('{caseId}', encodeURIComponent(input.caseId)), input);
  }
  E14(input: Operations['E14']['input']): Promise<Operations['E14']['output']> {
    return this.request("GET", "/api/v1/cases/{caseId}/packets".replace('{caseId}', encodeURIComponent(input.caseId)), input);
  }
  E15(input: Operations['E15']['input']): Promise<Operations['E15']['output']> {
    return this.request("GET", "/api/v1/cases/{caseId}/packets/{packetId}".replace('{caseId}', encodeURIComponent(input.caseId)).replace('{packetId}', encodeURIComponent(input.packetId)), input);
  }
  E16(input: Operations['E16']['input']): Promise<Operations['E16']['output']> {
    return this.request("PATCH", "/api/v1/cases/{caseId}/packets/{packetId}".replace('{caseId}', encodeURIComponent(input.caseId)).replace('{packetId}', encodeURIComponent(input.packetId)), input);
  }
  E17(input: Operations['E17']['input']): Promise<Operations['E17']['output']> {
    return this.request("POST", "/api/v1/cases/{caseId}/packets/{packetId}/approve".replace('{caseId}', encodeURIComponent(input.caseId)).replace('{packetId}', encodeURIComponent(input.packetId)), input);
  }
  E18(input: Operations['E18']['input']): Promise<Operations['E18']['output']> {
    return this.request("GET", "/api/v1/cases/{caseId}/packets/{packetId}/pdf".replace('{caseId}', encodeURIComponent(input.caseId)).replace('{packetId}', encodeURIComponent(input.packetId)), input);
  }
  E19(input: Operations['E19']['input']): Promise<Operations['E19']['output']> {
    return this.request("POST", "/api/v1/cases/{caseId}/packets/{packetId}/answer".replace('{caseId}', encodeURIComponent(input.caseId)).replace('{packetId}', encodeURIComponent(input.packetId)), input);
  }
  E20(input: Operations['E20']['input']): Promise<Operations['E20']['output']> {
    return this.request("GET", "/api/v1/cases/{caseId}/events".replace('{caseId}', encodeURIComponent(input.caseId)), input);
  }
  E21(input: Operations['E21']['input']): Promise<Operations['E21']['output']> {
    return this.request("GET", "/api/v1/cases/{caseId}/export".replace('{caseId}', encodeURIComponent(input.caseId)), input);
  }
  E22(input: Operations['E22']['input']): Promise<Operations['E22']['output']> {
    return this.request("GET", "/api/v1/console/cases", input);
  }
  E23(input: Operations['E23']['input']): Promise<Operations['E23']['output']> {
    return this.request("GET", "/api/v1/console/cases/{caseId}".replace('{caseId}', encodeURIComponent(input.caseId)), input);
  }
  E24(input: Operations['E24']['input']): Promise<Operations['E24']['output']> {
    return this.request("POST", "/api/v1/console/cases/{caseId}/packets/{packetId}/decision".replace('{caseId}', encodeURIComponent(input.caseId)).replace('{packetId}', encodeURIComponent(input.packetId)), input);
  }
  E25(input: Operations['E25']['input']): Promise<Operations['E25']['output']> {
    return this.request("GET", "/api/v1/console/cases/{caseId}/links".replace('{caseId}', encodeURIComponent(input.caseId)), input);
  }
  E26(input: Operations['E26']['input']): Promise<Operations['E26']['output']> {
    return this.request("POST", "/api/v1/console/links/{linkId}/validate".replace('{linkId}', encodeURIComponent(input.linkId)), input);
  }
  E27(input: Operations['E27']['input']): Promise<Operations['E27']['output']> {
    return this.request("GET", "/api/v1/packs", input);
  }
  E28(input: Operations['E28']['input']): Promise<Operations['E28']['output']> {
    return this.request("GET", "/api/v1/packs/{packId}/versions/{version}".replace('{packId}', encodeURIComponent(input.packId)).replace('{version}', encodeURIComponent(input.version)), input);
  }
  E29(input: Operations['E29']['input']): Promise<Operations['E29']['output']> {
    return this.request("POST", "/api/v1/sources", input);
  }
  E30(input: Operations['E30']['input']): Promise<Operations['E30']['output']> {
    return this.request("POST", "/api/v1/sources/{sourceId}/ingest".replace('{sourceId}', encodeURIComponent(input.sourceId)), input);
  }
  E31(input: Operations['E31']['input']): Promise<Operations['E31']['output']> {
    return this.request("GET", "/api/v1/sources/{sourceId}/passages".replace('{sourceId}', encodeURIComponent(input.sourceId)), input);
  }
  E32(input: Operations['E32']['input']): Promise<Operations['E32']['output']> {
    return this.request("POST", "/api/v1/pack-builds", input);
  }
  E33(input: Operations['E33']['input']): Promise<Operations['E33']['output']> {
    return this.request("GET", "/api/v1/pack-builds/{buildId}".replace('{buildId}', encodeURIComponent(input.buildId)), input);
  }
  E34(input: Operations['E34']['input']): Promise<Operations['E34']['output']> {
    return this.request("PATCH", "/api/v1/pack-builds/{buildId}/rules/{ruleId}".replace('{buildId}', encodeURIComponent(input.buildId)).replace('{ruleId}', encodeURIComponent(input.ruleId)), input);
  }
  E35(input: Operations['E35']['input']): Promise<Operations['E35']['output']> {
    return this.request("POST", "/api/v1/pack-builds/{buildId}/publish".replace('{buildId}', encodeURIComponent(input.buildId)), input);
  }
  E36(input: Operations['E36']['input']): Promise<Operations['E36']['output']> {
    return this.request("POST", "/api/v1/packs/{packId}/versions/{version}/retire".replace('{packId}', encodeURIComponent(input.packId)).replace('{version}', encodeURIComponent(input.version)), input);
  }
  E37(input: Operations['E37']['input']): Promise<Operations['E37']['output']> {
    return this.request("GET", "/api/v1/eval/runs", input);
  }
  E40(input: Operations['E40']['input']): Promise<Operations['E40']['output']> {
    return this.request("POST", "/api/v1/eval/runs", input);
  }
  E38(input: Operations['E38']['input']): Promise<Operations['E38']['output']> {
    return this.request("GET", "/api/v1/eval/runs/{runId}".replace('{runId}', encodeURIComponent(input.runId)), input);
  }
  E39(input: Operations['E39']['input']): Promise<Operations['E39']['output']> {
    return this.request("GET", "/api/v1/eval/runs/{runId}/failures".replace('{runId}', encodeURIComponent(input.runId)), input);
  }
  E41(input: Operations['E41']['input']): Promise<Operations['E41']['output']> {
    return this.request("POST", "/api/v1/demo/reset", input);
  }
  E42(input: Operations['E42']['input']): Promise<Operations['E42']['output']> {
    return this.request("POST", "/api/v1/demo/scenarios/{name}/load".replace('{name}', encodeURIComponent(input.name)), input);
  }
  E43(input: Operations['E43']['input']): Promise<Operations['E43']['output']> {
    return this.request("PUT", "/api/v1/demo/adapters/behavior", input);
  }
  E44_health(input: Operations['E44_health']['input']): Promise<Operations['E44_health']['output']> {
    return this.request("GET", "/api/v1/healthz", input);
  }
  E44_ready(input: Operations['E44_ready']['input']): Promise<Operations['E44_ready']['output']> {
    return this.request("GET", "/api/v1/readyz", input);
  }
  E44_version(input: Operations['E44_version']['input']): Promise<Operations['E44_version']['output']> {
    return this.request("GET", "/api/v1/version", input);
  }
  E45_generate(input: Operations['E45_generate']['input']): Promise<Operations['E45_generate']['output']> {
    return this.request("POST", "/api/v1/cases/{caseId}/packets/generate".replace('{caseId}', encodeURIComponent(input.caseId)), input);
  }
  E46_notifications(input: Operations['E46_notifications']['input']): Promise<Operations['E46_notifications']['output']> {
    return this.request("GET", "/api/v1/cases/{caseId}/notifications".replace('{caseId}', encodeURIComponent(input.caseId)), input);
  }
  E47_read(input: Operations['E47_read']['input']): Promise<Operations['E47_read']['output']> {
    return this.request("POST", "/api/v1/cases/{caseId}/notifications/{notificationId}/read".replace('{caseId}', encodeURIComponent(input.caseId)).replace('{notificationId}', encodeURIComponent(input.notificationId)), input);
  }
  E44_config(input: Operations['E44_config']['input']): Promise<Operations['E44_config']['output']> {
    return this.request("GET", "/api/v1/config/public", input);
  }
}
