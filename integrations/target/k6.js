import http from 'k6/http';
import { check, sleep } from 'k6';

if (!__ENV.BASE_URL) throw new Error('Set the explicitly owned BASE_URL');
export const options = {
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'],
    checks: ['rate==1'],
  },
};

export default function () {
  const response = http.get(__ENV.BASE_URL, { redirects: 0 });
  check(response, { 'home request succeeds': (r) => r.status === 200 });
  sleep(1);
}
