// Carga do DocExtract: cada VU cadastra um usuario, envia um documento e
// acompanha o job ate terminar.
//
//   k6 run bench/k6_upload.js -e BASE_URL=http://localhost:8000
//
// O limiar falha o teste se o upload passar de 800 ms no p95 ou se mais de
// 1% das requisicoes derem erro - e' o criterio que uso para dizer que uma
// mudanca de fila piorou a API.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

export const options = {
  scenarios: {
    upload: { executor: 'constant-vus', vus: 50, duration: '60s' },
  },
  thresholds: {
    'http_req_duration{fluxo:upload}': ['p(95)<800'],
    'http_req_failed': ['rate<0.01'],
    'job_concluido': ['rate>0.95'],
  },
};

const BASE = __ENV.BASE_URL || 'http://localhost:8000';
const CORPO = 'Processo SEI 1234.5678/2026-00\nCPF 435.004.468-09\n'.repeat(200);

export const jobConcluido = new Rate('job_concluido');
export const uploadMs = new Trend('upload_ms', true);

function cadastrar() {
  const email = `carga${__VU}-${__ITER}-${Date.now()}@exemplo.com`;
  const senha = 'senha-forte-123';
  http.post(`${BASE}/auth/register`, JSON.stringify({ email, password: senha }), {
    headers: { 'Content-Type': 'application/json' },
  });
  const login = http.post(`${BASE}/auth/login`, JSON.stringify({ email, password: senha }), {
    headers: { 'Content-Type': 'application/json' },
  });
  return { Authorization: `Bearer ${login.json('access_token')}` };
}

export default function () {
  const headers = cadastrar();
  const envio = http.post(
    `${BASE}/documents`,
    { arquivo: http.file(CORPO, 'relatorio.txt', 'text/plain') },
    { headers, tags: { fluxo: 'upload' } },
  );
  uploadMs.add(envio.timings.duration);

  if (envio.status !== 202) {
    jobConcluido.add(false);
    return;
  }

  const docId = envio.json('id');
  let pronto = false;
  for (let i = 0; i < 20; i++) {
    const consulta = http.get(`${BASE}/documents/${docId}`, { headers, tags: { fluxo: 'poll' } });
    const status = consulta.json('status');
    if (status === 'ready' || status === 'sem_texto' || status === 'error') {
      pronto = status !== 'error';
      break;
    }
    sleep(0.2);
  }
  jobConcluido.add(pronto);
  check(envio, { 'upload aceito': (r) => r.status === 202 });
}
